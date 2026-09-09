from __future__ import annotations
import asyncio
from time import monotonic
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from router.lifecycle.identity import IdentityOutcome, resolve_speaker_identity
from router.speaker_identity import SpeakerIdentityOutcome, SpeakerIdentityResult
from router.lifecycle.models import PersistedRequestState
from shared.protocol.context import (
    IdentityResolutionSource,
    OperationalContext,
    RequestContext,
    RequestType,
    ResolvedIdentity,
)
from shared.protocol.ids import new_span_id, new_trace_id
from shared.protocol.events import (
    IdentityFeedback,
    IdentityFeedbackEvent,
    InteractionState,
    InteractionStateChanged,
    SessionClosedEvent,
)
from shared.protocol.observability import LogKind, LogLevel, LogRecord
from shared.protocol.memory import MemoryRequirement, SemanticMemoryType
from shared.protocol.skills import SkillOutcome
from shared.protocol.requests import (
    CloseReason, ExecutionType, NyraRequest, NyraRequestResponse, NyraResponseBody, RequestStatus,
)


class LifecycleConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class ContextResult:
    data: dict[str, Any]
    semantic_memory_required: bool = False
    trace_id: str | None = None


class MemoryAccessError(RuntimeError):
    pass


@dataclass(frozen=True)
class MemoryQuery:
    query: str
    memory_types: tuple[SemanticMemoryType, ...] = ()
    limit: int = 10
    minimum_similarity: float = 0.35


@dataclass(frozen=True)
class SkillMatch:
    matched: bool
    token: str | None = None
    memory_requirement: MemoryRequirement = MemoryRequirement.NONE
    memory_query: MemoryQuery | str | None = None
    outcome: SkillOutcome = SkillOutcome.HANDLED
    text: str | None = None
    pending_state: dict[str, Any] | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class LifecycleDecision:
    status: RequestStatus
    text: str | None = None
    pending_state: dict[str, Any] | None = None
    close_reason: CloseReason | None = None
    error: dict[str, Any] | None = None
    llm_fallback: bool = False

    @classmethod
    def completed(cls, text: str | None = None):
        return cls(RequestStatus.COMPLETED, text=text)

    @classmethod
    def needs_clarification(cls, text: str, pending_state: dict[str, Any]):
        return cls(RequestStatus.NEEDS_CLARIFICATION, text=text, pending_state=pending_state)

    @classmethod
    def closed(cls, reason: CloseReason, text: str | None = None):
        return cls(RequestStatus.CLOSED, text=text, close_reason=reason)

    @classmethod
    def failed(cls, code: str):
        return cls(RequestStatus.FAILED, error={"code": code})


class SpeakerIdentityPort(Protocol):
    async def identify(self, request: NyraRequest, trace_id: str) -> SpeakerIdentityResult: ...


class ContextPort(Protocol):
    async def resolve(self, request: NyraRequest, identity_user_id: str | None, trace_id: str) -> ContextResult: ...


class MemoryPort(Protocol):
    async def search(self, request: NyraRequest, identity_user_id: str | None, query: MemoryQuery, trace_id: str) -> dict[str, Any]: ...


class SkillPort(Protocol):
    async def check(self, request: NyraRequest, context: ContextResult, memory: dict[str, Any] | None, pending_state: dict[str, Any] | None) -> SkillMatch: ...
    async def execute(self, match: SkillMatch, request: NyraRequest, context: ContextResult, memory: dict[str, Any] | None, pending_state: dict[str, Any] | None) -> LifecycleDecision: ...


class LlmPort(Protocol):
    async def reason(self, request: NyraRequest, context: ContextResult, memory: dict[str, Any] | None, pending_state: dict[str, Any] | None) -> LifecycleDecision: ...


class RequestLifecycleService:
    def __init__(self, store, broker, identity_port: SpeakerIdentityPort, context_port: ContextPort,
                 memory_port: MemoryPort, skill_port: SkillPort, llm_port: LlmPort,
                 clock=None, clarification_timeout_seconds: int = 120, observability=None,
                 identity_config=None, identification_timeout_seconds: float = 2.0,
                 user_directory=None):
        self.store = store
        self.broker = broker
        self.identity_port = identity_port
        self.context_port = context_port
        self.memory_port = memory_port
        self.skill_port = skill_port
        self.llm_port = llm_port
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.clarification_timeout_seconds = clarification_timeout_seconds
        self.observability = observability
        self.identity_config = identity_config
        self.identification_timeout_seconds = float(identification_timeout_seconds)
        self.user_directory = user_directory

    def _sync_trusted_identity(self, request: NyraRequest) -> None:
        identity = request.identity
        if (
            self.user_directory is None
            or identity is None
            or identity.display_name is None
        ):
            return
        try:
            self.user_directory.upsert(
                identity.provider, identity.user_id, identity.display_name
            )
        except Exception:
            pass

    def _identity_display_name(
        self, request: NyraRequest, identity_user_id: str | None
    ) -> str | None:
        if identity_user_id in (None, "guest"):
            return None
        if (
            request.identity is not None
            and request.identity.user_id == identity_user_id
            and request.identity.display_name is not None
        ):
            return request.identity.display_name
        if self.user_directory is None:
            return None
        try:
            reference = self.user_directory.get("home_assistant", identity_user_id)
        except Exception:
            return None
        return reference.display_name if reference is not None else None

    def _log(self, request: NyraRequest, trace_id: str, span_id: str, event: str,
             kind: LogKind = LogKind.EVENT, result: str | None = None,
             payload: Any = None, params: dict[str, Any] | None = None,
             span_elapsed_ms: float | None = None) -> None:
        if self.observability is None:
            return
        self.observability.ingest([LogRecord(
            ct="ROUTER",
            level=LogLevel.INFO,
            kind=kind,
            event=event,
            session_id=request.session_id,
            request_id=request.request_id,
            trace_id=trace_id,
            span_id=span_id,
            origin_request_id=request.origin_request_id,
            operation="request_lifecycle",
            result=result,
            span_elapsed_ms=span_elapsed_ms,
            params=params or {},
            payload=payload,
        )])

    async def _state(self, request: NyraRequest, trace_id: str, span_id: str, state: InteractionState):
        await self.broker.publish_state(InteractionStateChanged(
            state=state, source=request.source, session_id=request.session_id,
            request_id=request.request_id, trace_id=trace_id,
        ))
        self._log(request, trace_id, span_id, "INTERACTION_STATE_CHANGED", result=state.value,
                  params={"state": state.value, "source_id": request.source.id if request.source else None})

    def _build_request_context(
        self,
        request: NyraRequest,
        trace_id: str,
        identity_user_id: str | None,
        context: ContextResult,
        previous_session_state: PersistedRequestState | None = None,
        identity_source: IdentityResolutionSource | None = None,
    ) -> RequestContext:
        if identity_source is None:
            if request.identity is not None:
                identity_source = IdentityResolutionSource.TRUSTED_HA_IDENTITY
            elif request.type is ExecutionType.HA_SPEAKER and identity_user_id not in (None, "guest"):
                identity_source = IdentityResolutionSource.SPEAKER_IDENTIFICATION
            else:
                identity_source = IdentityResolutionSource.GUEST_FALLBACK

        identity = None
        if request.type is not ExecutionType.JOB:
            identity = ResolvedIdentity(
                user_id=identity_user_id or "guest",
                resolution_source=identity_source,
                display_name=self._identity_display_name(request, identity_user_id),
            )

        return RequestContext(
            session_id=request.session_id,
            request_id=request.request_id,
            origin_request_id=request.origin_request_id,
            trace_id=trace_id,
            type=RequestType(request.type.value),
            language=request.language,
            source=request.source.id if request.source else None,
            area=request.source.area if request.source else None,
            identity=identity,
            operational=OperationalContext(values=context.data),
        )

    async def execute(self, request: NyraRequest) -> NyraRequestResponse:
        trace_id = new_trace_id()
        span_id = new_span_id("ROUTER", "request_lifecycle")
        started = monotonic()
        self._log(request, trace_id, span_id, "REQUEST_RECEIVED", kind=LogKind.REQUEST,
                  payload={"type": request.type.value, "language": request.language,
                           "source": request.source.model_dump(mode="json") if request.source else None,
                           "input": request.input.model_dump(mode="json")})
        try:
            response = await self._execute(request, trace_id, span_id)
        except Exception as exc:
            self._log(request, trace_id, span_id, "REQUEST_FAILED", kind=LogKind.FAULT,
                      result="failed", params={"error_type": type(exc).__name__},
                      span_elapsed_ms=(monotonic() - started) * 1000)
            raise
        terminal_kind = LogKind.FAULT if response.status is RequestStatus.FAILED else LogKind.RESPONSE
        terminal_event = "REQUEST_FAILED" if response.status is RequestStatus.FAILED else "REQUEST_COMPLETED"
        self._log(request, trace_id, span_id, terminal_event, kind=terminal_kind,
                  result=response.status.value,
                  payload=response.model_dump(mode="json"),
                  span_elapsed_ms=(monotonic() - started) * 1000)
        return response

    async def _execute(self, request: NyraRequest, trace_id: str, span_id: str) -> NyraRequestResponse:
        now = self.clock()
        self._sync_trusted_identity(request)
        existing = None
        pending_state = None

        if request.request_id is not None:
            self.store.expire_due(now)
            existing = self.store.get(request.request_id)
            if existing is not None:
                if existing.session_id != request.session_id:
                    raise LifecycleConflict("request_id belongs to a different session")
                if existing.status is RequestStatus.EXPIRED:
                    return NyraRequestResponse(
                        status=RequestStatus.EXPIRED, session_id=request.session_id,
                        request_id=request.request_id, trace_id=trace_id,
                    )
                if existing.status is not RequestStatus.NEEDS_CLARIFICATION:
                    raise LifecycleConflict(f"request cannot resume from status {existing.status.value}")
                pending_state = existing.pending_state

        await self._state(request, trace_id, span_id, InteractionState.PROCESSING_LOCAL)

        previous_session_state = None
        if request.session_id is not None and existing is None:
            previous_session_state = self.store.get_latest_for_session(request.session_id)
        last_trusted_user_id = request.identity.user_id if request.identity else (
            existing.last_trusted_user_id if existing else (
                previous_session_state.last_trusted_user_id if previous_session_state else None
            )
        )
        identity_user_id = request.identity.user_id if request.identity else (
            existing.identity_user_id if existing else last_trusted_user_id
        )
        identity_source = (
            IdentityResolutionSource.TRUSTED_HA_IDENTITY
            if request.identity is not None
            else None
        )

        if request.type is ExecutionType.HA_SPEAKER:
            await self._state(request, trace_id, span_id, InteractionState.IDENTIFYING)
            snapshot = self.identity_config.snapshot() if self.identity_config is not None else None
            timeout_seconds = (
                snapshot.identification_timeout_seconds
                if snapshot is not None
                else self.identification_timeout_seconds
            )
            identity_started = monotonic()
            identity_source_id = request.source.id if request.source else None
            self._log(
                request,
                trace_id,
                span_id,
                "identity.started",
                params={
                    "source_id": identity_source_id,
                    "config_revision": snapshot.revision if snapshot is not None else None,
                    "timeout_seconds": timeout_seconds,
                },
            )
            identity_task = asyncio.create_task(self.identity_port.identify(request, trace_id))
            done, _ = await asyncio.wait({identity_task}, timeout=timeout_seconds)
            timed_out = identity_task not in done

            if timed_out:
                def _consume_late_identity(task):
                    try:
                        late_result = task.result()
                    except BaseException:
                        return
                    if isinstance(late_result, str):
                        late_result = SpeakerIdentityResult(
                            outcome=SpeakerIdentityOutcome.IDENTIFIED,
                            identified_user_id=late_result,
                            best_score=None,
                            diagnostic_id=None,
                            reason_code=None,
                        )
                    if isinstance(late_result, SpeakerIdentityResult):
                        self._log_identity_completed(
                            request,
                            trace_id,
                            span_id,
                            late_result,
                            identity_source_id,
                            identity_started,
                            late_result=True,
                        )
                identity_task.add_done_callback(_consume_late_identity)
                raw_identity_result = None
            else:
                try:
                    raw_identity_result = identity_task.result()
                except Exception:
                    raw_identity_result = SpeakerIdentityResult(
                        outcome=SpeakerIdentityOutcome.FAILED,
                        identified_user_id=None,
                        best_score=None,
                        diagnostic_id=None,
                        reason_code="SERVICE_UNAVAILABLE",
                    )

            if isinstance(raw_identity_result, SpeakerIdentityResult):
                identity_result = raw_identity_result
            elif isinstance(raw_identity_result, str):
                identity_result = SpeakerIdentityResult(
                    outcome=SpeakerIdentityOutcome.IDENTIFIED,
                    identified_user_id=raw_identity_result,
                    best_score=None,
                    diagnostic_id=None,
                    reason_code=None,
                )
            else:
                identity_result = None

            if not timed_out and identity_result is not None:
                self._log_identity_completed(
                    request,
                    trace_id,
                    span_id,
                    identity_result,
                    identity_source_id,
                    identity_started,
                    late_result=False,
                )

            resolution = resolve_speaker_identity(
                last_trusted_user_id,
                identity_result,
                timed_out=timed_out,
            )
            identity_user_id = resolution.current_user_id
            last_trusted_user_id = resolution.last_trusted_user_id
            identity_source = resolution.resolution_source

            self._log(
                request,
                trace_id,
                span_id,
                "identity.resolved",
                result=resolution.current_user_id,
                params={
                    "source_id": identity_source_id,
                    "user_id": resolution.current_user_id,
                    "resolution": resolution.resolution_source.value,
                    "biometric_outcome": (
                        identity_result.outcome.value if identity_result is not None else None
                    ),
                    "timed_out": timed_out,
                },
            )

            self._log(
                request,
                trace_id,
                span_id,
                resolution.outcome.value,
                result=resolution.current_user_id,
                params={
                    "previous_user_id": resolution.previous_user_id,
                    "current_user_id": resolution.current_user_id,
                    "last_trusted_user_id": resolution.last_trusted_user_id,
                    "timed_out": resolution.timed_out,
                    "speaker_identity_outcome": (
                        identity_result.outcome.value
                        if identity_result is not None
                        else None
                    ),
                    "config_revision": snapshot.revision if snapshot is not None else None,
                },
            )

            feedback = {
                IdentityOutcome.IDENTIFIED: IdentityFeedback.RECOGNIZED,
                IdentityOutcome.CONFIRMED: IdentityFeedback.RECOGNIZED,
                IdentityOutcome.CHANGED: IdentityFeedback.IDENTITY_CHANGED,
                IdentityOutcome.CONTINUITY: IdentityFeedback.NOT_RECOGNIZED,
                IdentityOutcome.GUEST: IdentityFeedback.NOT_RECOGNIZED,
            }[resolution.outcome]
            await self.broker.publish_identity_feedback(IdentityFeedbackEvent(
                feedback=feedback,
                source=request.source,
                session_id=request.session_id,
                request_id=request.request_id,
                trace_id=trace_id,
            ))
            await self._state(request, trace_id, span_id, InteractionState.PROCESSING_LOCAL)

        context = await self.context_port.resolve(request, identity_user_id, trace_id)
        request_context = self._build_request_context(
            request,
            trace_id,
            identity_user_id,
            context,
            previous_session_state,
            identity_source,
        )
        context_data = dict(context.data)
        if request_context.identity is not None:
            context_data["identity"] = {
                "user_id": request_context.identity.user_id,
                "display_name": request_context.identity.display_name,
                "resolution_source": request_context.identity.resolution_source.value,
            }
        context = ContextResult(
            data=context_data,
            semantic_memory_required=context.semantic_memory_required,
            trace_id=trace_id,
        )
        memory = None
        match = await self.skill_port.check(request, context, None, pending_state)
        if match.outcome is SkillOutcome.NEEDS_CLARIFICATION:
            decision = LifecycleDecision.needs_clarification(
                match.text or "",
                match.pending_state or {},
            )
        elif match.outcome is SkillOutcome.FAILED:
            decision = LifecycleDecision.failed(
                match.error_code or "SKILLS_FAILED"
            )
        elif match.outcome is SkillOutcome.MISS:
            self._log(
                request,
                trace_id,
                span_id,
                "MEMORY_SEARCH_SKIPPED",
                params={"reason": "SKILL_MISS"},
            )
            await self._state(
                request,
                trace_id,
                span_id,
                InteractionState.PROCESSING_GLOBAL,
            )
            decision = await self.llm_port.reason(
                request,
                context,
                memory,
                pending_state,
            )
        elif match.matched:
            if match.memory_requirement is MemoryRequirement.NONE:
                self._log(
                    request, trace_id, span_id, "MEMORY_SEARCH_SKIPPED",
                    params={"requirement": MemoryRequirement.NONE.value},
                )
            else:
                raw_query = match.memory_query
                query = (
                    raw_query
                    if isinstance(raw_query, MemoryQuery)
                    else MemoryQuery(query=raw_query or request.input.text)
                )
                self._log(
                    request, trace_id, span_id, "MEMORY_SEARCH_START",
                    params={"requirement": match.memory_requirement.value},
                )
                try:
                    memory = await self.memory_port.search(
                        request, identity_user_id, query, trace_id
                    )
                    self._log(
                        request, trace_id, span_id, "MEMORY_SEARCH_COMPLETED",
                        result="SUCCESS",
                        params={
                            "requirement": match.memory_requirement.value,
                            "result_count": len(memory.get("items", [])),
                        },
                    )
                except MemoryAccessError as exc:
                    self._log(
                        request, trace_id, span_id, "MEMORY_SEARCH_FAILED",
                        kind=LogKind.FAULT,
                        result=type(exc).__name__,
                        params={"requirement": match.memory_requirement.value},
                    )
                    if match.memory_requirement is MemoryRequirement.REQUIRED:
                        decision = LifecycleDecision.failed("MEMORY_UNAVAILABLE")
                    else:
                        decision = None
                else:
                    decision = None
            if match.memory_requirement is MemoryRequirement.NONE:
                decision = None
            if decision is None:
                decision = await self.skill_port.execute(
                    match,
                    request,
                    context,
                    memory,
                    pending_state,
                )
            if decision.llm_fallback:
                await self._state(
                    request,
                    trace_id,
                    span_id,
                    InteractionState.PROCESSING_GLOBAL,
                )
                decision = await self.llm_port.reason(
                    request,
                    context,
                    memory,
                    pending_state,
                )
        else:
            self._log(
                request, trace_id, span_id, "MEMORY_SEARCH_SKIPPED",
                params={"reason": "NO_SKILL_MATCH"},
            )
            await self._state(request, trace_id, span_id, InteractionState.PROCESSING_GLOBAL)
            decision = await self.llm_port.reason(request, context, memory, pending_state)

        if request_context.request_id is not None:
            if existing is None:
                persisted = PersistedRequestState(
                    request_id=request_context.request_id,
                    session_id=request_context.session_id,
                    type=request.type,
                    language=request_context.language,
                    source=request.source,
                    identity_user_id=request_context.identity.user_id if request_context.identity else None,
                    last_trusted_user_id=last_trusted_user_id,
                    original_input=request.input.text,
                    status=decision.status,
                    current_trace_id=request_context.trace_id,
                    pending_state=decision.pending_state,
                    created_at=now,
                    updated_at=now,
                    expires_at=(now + timedelta(seconds=self.clarification_timeout_seconds)) if decision.status is RequestStatus.NEEDS_CLARIFICATION else None,
                )
                self.store.create(persisted)
            else:
                existing.identity_user_id = request_context.identity.user_id if request_context.identity else None
                existing.last_trusted_user_id = last_trusted_user_id
                existing.status = decision.status
                existing.current_trace_id = request_context.trace_id
                existing.pending_state = decision.pending_state
                existing.updated_at = now
                existing.expires_at = (now + timedelta(seconds=self.clarification_timeout_seconds)) if decision.status is RequestStatus.NEEDS_CLARIFICATION else None
                self.store.update(existing)

        if decision.status is RequestStatus.NEEDS_CLARIFICATION:
            await self._state(request, trace_id, span_id, InteractionState.WAITING_CLARIFICATION)
        elif decision.status is RequestStatus.CLOSED:
            closed_event = SessionClosedEvent(
                close_reason=decision.close_reason,
                source=request.source,
                session_id=request_context.session_id,
                request_id=request_context.request_id,
                trace_id=request_context.trace_id,
            )
            await self.broker.publish_session_closed(closed_event)
            self._log(request, trace_id, span_id, "SESSION_CLOSED", result=decision.close_reason.value,
                      params={"close_reason": decision.close_reason.value})

        return NyraRequestResponse(
            status=decision.status,
            session_id=request_context.session_id,
            request_id=request_context.request_id,
            trace_id=request_context.trace_id,
            response=NyraResponseBody(text=decision.text) if decision.text is not None else None,
            close_reason=decision.close_reason,
            error=decision.error,
        )

    def _log_identity_completed(
        self,
        request: NyraRequest,
        trace_id: str,
        span_id: str,
        result: SpeakerIdentityResult,
        source_id: str | None,
        started: float,
        *,
        late_result: bool,
    ) -> None:
        self._log(
            request,
            trace_id,
            span_id,
            "identity.completed",
            result=result.outcome.value,
            params={
                "source_id": source_id,
                "outcome": result.outcome.value,
                "identified_user_id": result.identified_user_id,
                "best_score": result.best_score,
                "diagnostic_id": result.diagnostic_id,
                "reason_code": result.reason_code,
                "latency_ms": max(0.0, (monotonic() - started) * 1000),
                "late_result": late_result,
            },
        )
