from __future__ import annotations
import asyncio
from time import monotonic
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from router.lifecycle.identity import resolve_identity_outcome
from router.lifecycle.models import PersistedRequestState
from router.observability.ids import generate_span_id, generate_trace_id
from shared.protocol.events import InteractionState, InteractionStateChanged, SessionClosedEvent
from shared.protocol.observability import LogKind, LogLevel, LogRecord
from shared.protocol.requests import (
    CloseReason, ExecutionType, NyraRequest, NyraRequestResponse, NyraResponseBody, RequestStatus,
)


class LifecycleConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class ContextResult:
    data: dict[str, Any]
    semantic_memory_required: bool = False


@dataclass(frozen=True)
class SkillMatch:
    matched: bool
    token: str | None = None


@dataclass(frozen=True)
class LifecycleDecision:
    status: RequestStatus
    text: str | None = None
    pending_state: dict[str, Any] | None = None
    close_reason: CloseReason | None = None

    @classmethod
    def completed(cls, text: str | None = None):
        return cls(RequestStatus.COMPLETED, text=text)

    @classmethod
    def needs_clarification(cls, text: str, pending_state: dict[str, Any]):
        return cls(RequestStatus.NEEDS_CLARIFICATION, text=text, pending_state=pending_state)

    @classmethod
    def closed(cls, reason: CloseReason, text: str | None = None):
        return cls(RequestStatus.CLOSED, text=text, close_reason=reason)


class SpeakerIdentityPort(Protocol):
    async def identify(self, request: NyraRequest, trace_id: str) -> str | None: ...


class ContextPort(Protocol):
    async def resolve(self, request: NyraRequest, identity_user_id: str | None) -> ContextResult: ...


class MemoryPort(Protocol):
    async def search(self, request: NyraRequest, identity_user_id: str | None, context: ContextResult) -> dict[str, Any]: ...


class SkillPort(Protocol):
    async def check(self, request: NyraRequest, context: ContextResult, memory: dict[str, Any] | None, pending_state: dict[str, Any] | None) -> SkillMatch: ...
    async def execute(self, match: SkillMatch, request: NyraRequest, context: ContextResult, memory: dict[str, Any] | None, pending_state: dict[str, Any] | None) -> LifecycleDecision: ...


class LlmPort(Protocol):
    async def reason(self, request: NyraRequest, context: ContextResult, memory: dict[str, Any] | None, pending_state: dict[str, Any] | None) -> LifecycleDecision: ...


class RequestLifecycleService:
    def __init__(self, store, broker, identity_port: SpeakerIdentityPort, context_port: ContextPort,
                 memory_port: MemoryPort, skill_port: SkillPort, llm_port: LlmPort,
                 clock=None, clarification_timeout_seconds: int = 120, observability=None):
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

    async def execute(self, request: NyraRequest) -> NyraRequestResponse:
        trace_id = generate_trace_id()
        span_id = generate_span_id("ROUTER", "request_lifecycle")
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
        self._log(request, trace_id, span_id, "REQUEST_COMPLETED", kind=LogKind.RESPONSE,
                  result=response.status.value,
                  payload=response.model_dump(mode="json"),
                  span_elapsed_ms=(monotonic() - started) * 1000)
        return response

    async def _execute(self, request: NyraRequest, trace_id: str, span_id: str) -> NyraRequestResponse:
        now = self.clock()
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

        await self._state(request, trace_id, span_id, InteractionState.PROCESSING)

        previous_session_state = None
        if request.session_id is not None and existing is None:
            previous_session_state = self.store.get_latest_for_session(request.session_id)
        identity_user_id = request.identity.user_id if request.identity else (
            existing.identity_user_id if existing else (previous_session_state.identity_user_id if previous_session_state else None)
        )
        identity_task = None
        if request.type is ExecutionType.HA_SPEAKER:
            await self._state(request, trace_id, span_id, InteractionState.IDENTIFYING)
            identity_task = asyncio.create_task(self.identity_port.identify(request, trace_id))

        await self._state(request, trace_id, span_id, InteractionState.MEMORY)
        context = await self.context_port.resolve(request, identity_user_id)

        if identity_task is not None:
            detected = await identity_task
            resolution = resolve_identity_outcome(identity_user_id, detected)
            identity_user_id = resolution.current_user_id
            self._log(request, trace_id, span_id, resolution.outcome.value,
                      result=resolution.current_user_id,
                      params={"previous_user_id": resolution.previous_user_id,
                              "current_user_id": resolution.current_user_id})

        memory = None
        if context.semantic_memory_required:
            self._log(request, trace_id, span_id, "MEMORY_SEARCH", params={"required": True})
            memory = await self.memory_port.search(request, identity_user_id, context)

        await self._state(request, trace_id, span_id, InteractionState.SKILL_CHECK)
        match = await self.skill_port.check(request, context, memory, pending_state)
        if match.matched:
            await self._state(request, trace_id, span_id, InteractionState.SKILL_EXECUTION)
            decision = await self.skill_port.execute(match, request, context, memory, pending_state)
        else:
            await self._state(request, trace_id, span_id, InteractionState.LLM_REASONING)
            decision = await self.llm_port.reason(request, context, memory, pending_state)

        if request.request_id is not None:
            if existing is None:
                persisted = PersistedRequestState(
                    request_id=request.request_id,
                    session_id=request.session_id,
                    type=request.type,
                    language=request.language,
                    source=request.source,
                    identity_user_id=identity_user_id,
                    original_input=request.input.text,
                    status=decision.status,
                    current_trace_id=trace_id,
                    pending_state=decision.pending_state,
                    created_at=now,
                    updated_at=now,
                    expires_at=(now + timedelta(seconds=self.clarification_timeout_seconds)) if decision.status is RequestStatus.NEEDS_CLARIFICATION else None,
                )
                self.store.create(persisted)
            else:
                existing.identity_user_id = identity_user_id
                existing.status = decision.status
                existing.current_trace_id = trace_id
                existing.pending_state = decision.pending_state
                existing.updated_at = now
                existing.expires_at = (now + timedelta(seconds=self.clarification_timeout_seconds)) if decision.status is RequestStatus.NEEDS_CLARIFICATION else None
                self.store.update(existing)

        if decision.status is RequestStatus.NEEDS_CLARIFICATION:
            await self._state(request, trace_id, span_id, InteractionState.NEEDS_CLARIFICATION)
        elif decision.status is RequestStatus.CLOSED:
            closed_event = SessionClosedEvent(
                close_reason=decision.close_reason,
                source=request.source,
                session_id=request.session_id,
                request_id=request.request_id,
                trace_id=trace_id,
            )
            await self.broker.publish_session_closed(closed_event)
            self._log(request, trace_id, span_id, "SESSION_CLOSED", result=decision.close_reason.value,
                      params={"close_reason": decision.close_reason.value})

        return NyraRequestResponse(
            status=decision.status,
            session_id=request.session_id,
            request_id=request.request_id,
            trace_id=trace_id,
            response=NyraResponseBody(text=decision.text) if decision.text is not None else None,
            close_reason=decision.close_reason,
        )
