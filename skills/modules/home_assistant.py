from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import httpx

from shared.protocol.capabilities import (
    CapabilityCorrelation,
    ExecuteRequest,
    ExecuteResponse,
    ResolveCardinality,
    ResolveResponse,
    ResolveStatus,
    ResourceReference,
)
from shared.protocol.common import CommonOutcome, ErrorDetail
from shared.protocol.execution_common import NyraOperation, NyraResourceType
from shared.protocol.memory import MemoryRequirement
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillExecuteRequest,
    SkillExecuteResponse,
    SkillMatch,
    SkillOutcome,
)


@dataclass(frozen=True)
class ParsedHomeAssistantCommand:
    operation: NyraOperation
    resource_type: NyraResourceType
    reference: str


class RouterHomeAssistantCapabilityClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.transport = transport

    async def resolve(
        self,
        reference: ResourceReference,
        trusted_context: dict[str, Any],
        *,
        correlation: CapabilityCorrelation,
    ) -> ResolveResponse:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
        ) as client:
            response = await client.post(
                "/v1/capabilities/home-assistant/resolve",
                json={
                    "correlation": correlation.model_dump(mode="json"),
                    "reference": reference.model_dump(mode="json"),
                    "trusted_context": trusted_context,
                },
            )
            response.raise_for_status()
        return ResolveResponse.model_validate(response.json())

    async def execute(
        self,
        request: ExecuteRequest,
        trusted_context: dict[str, Any],
    ) -> ExecuteResponse:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
        ) as client:
            response = await client.post(
                "/v1/capabilities/home-assistant/execute",
                json={
                    "request": request.model_dump(mode="json"),
                    "trusted_context": trusted_context,
                },
            )
            response.raise_for_status()
        return ExecuteResponse.model_validate(response.json())


_ACTIONS = {
    "en": (
        (re.compile(r"^turn on (?:the )?(.+)$"), NyraOperation.TURN_ON),
        (re.compile(r"^turn off (?:the )?(.+)$"), NyraOperation.TURN_OFF),
        (re.compile(r"^open (?:the )?(.+)$"), NyraOperation.OPEN),
        (re.compile(r"^close (?:the )?(.+)$"), NyraOperation.CLOSE),
    ),
    "it": (
        (re.compile(r"^accendi (?:la |il |lo |l )?(.+)$"), NyraOperation.TURN_ON),
        (re.compile(r"^spegni (?:la |il |lo |l )?(.+)$"), NyraOperation.TURN_OFF),
        (re.compile(r"^apri (?:la |il |lo |l )?(.+)$"), NyraOperation.OPEN),
        (re.compile(r"^chiudi (?:la |il |lo |l )?(.+)$"), NyraOperation.CLOSE),
    ),
}

_RESOURCE_TERMS = {
    "en": (
        (NyraResourceType.LIGHT, {"light", "lamp"}),
        (NyraResourceType.SWITCH, {"switch"}),
        (NyraResourceType.COVER, {"blind", "cover", "shutter"}),
    ),
    "it": (
        (NyraResourceType.LIGHT, {"luce", "lampada"}),
        (NyraResourceType.SWITCH, {"interruttore"}),
        (NyraResourceType.COVER, {"tenda", "tapparella"}),
    ),
}


_STOP_WORDS = {
    "en": {"the", "one", "that", "this", "of", "in", "on"},
    "it": {
        "quella", "quello", "quell", "della", "dello", "del", "di",
        "la", "il", "lo", "l", "una", "uno",
    },
}

_CONTINUATION_PREFIXES = {
    "en": ("the ", "that ", "this "),
    "it": ("quella ", "quello ", "quell "),
}


def _language(value: str) -> str:
    language = value.split("-", 1)[0].lower()
    return language if language in _ACTIONS else "en"


def _normalized(value: str) -> str:
    return " ".join(
        re.sub(r"[^\w]+", " ", value.casefold()).split()
    )


def _meaningful_tokens(value: str, language: str) -> set[str]:
    return {
        token
        for token in _normalized(value).split()
        if token not in _STOP_WORDS[language]
    }


def _clarification_state(
    pending_state: dict[str, Any] | None,
    skill_name: str,
) -> dict[str, Any] | None:
    if not isinstance(pending_state, dict):
        return None
    if pending_state.get("kind") != "ha_target_clarification":
        return None
    if pending_state.get("skill_name") != skill_name:
        return None
    candidates = pending_state.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return None
    return pending_state


def _candidate_name(candidate: dict[str, Any]) -> str | None:
    name = candidate.get("name")
    if isinstance(name, str) and name.strip():
        return " ".join(name.split())
    return None


def _select_candidate(
    text: str,
    language: str,
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    query_tokens = _meaningful_tokens(text, language)
    scored: list[tuple[int, str, dict[str, Any]]] = []

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        name = _candidate_name(candidate)
        if name is None:
            continue
        score = len(query_tokens & _meaningful_tokens(name, language))
        if score > 0:
            scored.append((score, name.casefold(), candidate))

    if not scored:
        return None

    scored.sort(key=lambda item: (-item[0], item[1]))
    best_score = scored[0][0]
    best = [item for item in scored if item[0] == best_score]
    if len(best) != 1:
        return None
    return best[0][2]


def _clarification_prompt(
    candidates: list[dict[str, Any]],
    language: str,
) -> str:
    names = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        name = _candidate_name(candidate)
        if name is not None and name not in names:
            names.append(name)

    if not names:
        return (
            "Quale dispositivo intendi?"
            if language == "it"
            else "Which device do you mean?"
        )

    if len(names) == 1:
        choices = names[0]
    else:
        separator = " o " if language == "it" else " or "
        choices = ", ".join(names[:-1]) + separator + names[-1]

    return (
        f"Quale dispositivo intendi: {choices}?"
        if language == "it"
        else f"Which device do you mean: {choices}?"
    )


def _resource_type(language: str, reference: str) -> NyraResourceType | None:
    tokens = set(_normalized(reference).split())
    for resource_type, terms in _RESOURCE_TERMS[language]:
        if tokens & terms:
            return resource_type
    return None


def parse_command(text: str, language: str) -> ParsedHomeAssistantCommand | None:
    selected_language = _language(language)
    normalized = _normalized(text)

    for pattern, operation in _ACTIONS[selected_language]:
        match = pattern.fullmatch(normalized)
        if match is None:
            continue

        reference = " ".join(match.group(1).split())
        resource_type = _resource_type(selected_language, reference)
        if resource_type is None:
            return None

        if operation in {NyraOperation.OPEN, NyraOperation.CLOSE}:
            if resource_type is not NyraResourceType.COVER:
                return None
        elif resource_type is NyraResourceType.COVER:
            return None

        return ParsedHomeAssistantCommand(
            operation=operation,
            resource_type=resource_type,
            reference=reference,
        )

    return None


class HomeAssistantActionSkill:
    name = "home_assistant_action"
    priority = 90

    def __init__(self, capability: RouterHomeAssistantCapabilityClient) -> None:
        self.capability = capability

    def matches(self, request: SkillCheckRequest) -> bool:
        if parse_command(request.text, request.language) is not None:
            return True

        state = _clarification_state(request.pending_state, self.name)
        if state is None:
            return False

        language = _language(request.language)
        candidates = state["candidates"]
        if _select_candidate(request.text, language, candidates) is not None:
            return True

        normalized = _normalized(request.text)
        return normalized.startswith(_CONTINUATION_PREFIXES[language])

    def match(self, request: SkillCheckRequest) -> SkillMatch:
        parsed = parse_command(request.text, request.language)
        if parsed is not None:
            return SkillMatch(
                matched=True,
                skill_name=self.name,
                token=self.name,
                memory_requirement=MemoryRequirement.NONE,
                metadata={
                    "operation": parsed.operation.value,
                    "resource_type": parsed.resource_type.value,
                    "reference": parsed.reference,
                },
            )

        state = _clarification_state(request.pending_state, self.name)
        if state is None:
            return SkillMatch(matched=False)

        language = _language(request.language)
        selected = _select_candidate(
            request.text,
            language,
            state["candidates"],
        )
        metadata = {
            "operation": state.get("operation"),
            "resource_type": state.get("resource_type"),
            "reference": state.get("reference"),
            "clarification": True,
        }
        if selected is not None:
            metadata["selected_resource_id"] = selected.get("resource_id")
            metadata["selected_resource_type"] = selected.get("resource_type")
            metadata["selected_name"] = selected.get("name")

        return SkillMatch(
            matched=True,
            skill_name=self.name,
            token=self.name,
            memory_requirement=MemoryRequirement.NONE,
            metadata=metadata,
        )

    async def execute(
        self,
        request: SkillExecuteRequest,
    ) -> SkillExecuteResponse:
        metadata = request.match.metadata
        try:
            operation = NyraOperation(metadata["operation"])
            resource_type = NyraResourceType(metadata["resource_type"])
            reference_text = str(metadata["reference"])
        except (KeyError, TypeError, ValueError):
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code="INVALID_HA_SKILL_MATCH"),
            )

        correlation = CapabilityCorrelation(
            **request.correlation.model_dump()
        )
        trusted_context = dict(request.context)
        language = _language(request.language)

        selected_resource_id = metadata.get("selected_resource_id")
        selected_resource_type = metadata.get("selected_resource_type")
        if isinstance(selected_resource_id, str):
            try:
                target_type = NyraResourceType(selected_resource_type)
            except (TypeError, ValueError):
                return SkillExecuteResponse(
                    correlation=request.correlation,
                    outcome=SkillOutcome.FAILED,
                    error=ErrorDetail(code="INVALID_HA_CLARIFICATION_TARGET"),
                )

            executed = await self.capability.execute(
                ExecuteRequest(
                    correlation=correlation,
                    operation=operation,
                    resource_id=selected_resource_id,
                    resource_type=target_type,
                ),
                trusted_context,
            )
            if executed.outcome is not CommonOutcome.SUCCESS:
                return SkillExecuteResponse(
                    correlation=request.correlation,
                    outcome=SkillOutcome.FAILED,
                    error=executed.error
                    or ErrorDetail(code=f"HA_{executed.outcome.value}"),
                )

            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.HANDLED,
                text="Fatto." if language == "it" else "Done.",
                result={
                    "operation": operation.value,
                    "resource_type": target_type.value,
                    "resource_id": selected_resource_id,
                    "reference": reference_text,
                },
            )

        state = _clarification_state(request.pending_state, self.name)
        if metadata.get("clarification") and state is not None:
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.NEEDS_CLARIFICATION,
                text=_clarification_prompt(state["candidates"], language),
                pending_state=state,
            )

        resolved = await self.capability.resolve(
            ResourceReference(
                reference=reference_text,
                resource_type=resource_type,
                cardinality=ResolveCardinality.ONE,
            ),
            trusted_context,
            correlation=correlation,
        )

        if resolved.status is ResolveStatus.NOT_FOUND:
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code="HA_TARGET_NOT_FOUND"),
            )

        if resolved.status is ResolveStatus.AMBIGUOUS:
            candidates = [
                {
                    "resource_id": candidate.resource.resource_id,
                    "resource_type": candidate.resource.resource_type.value,
                    "name": candidate.resource.name,
                }
                for candidate in resolved.candidates
            ]
            pending_state = {
                "kind": "ha_target_clarification",
                "skill_name": self.name,
                "operation": operation.value,
                "resource_type": resource_type.value,
                "reference": reference_text,
                "candidates": candidates,
            }
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.NEEDS_CLARIFICATION,
                text=_clarification_prompt(candidates, language),
                pending_state=pending_state,
            )

        if len(resolved.candidates) != 1:
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code="HA_INVALID_RESOLVE_RESULT"),
            )

        target = resolved.candidates[0].resource
        executed = await self.capability.execute(
            ExecuteRequest(
                correlation=correlation,
                operation=operation,
                resource_id=target.resource_id,
                resource_type=target.resource_type,
            ),
            trusted_context,
        )

        if executed.outcome is not CommonOutcome.SUCCESS:
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=executed.error
                or ErrorDetail(code=f"HA_{executed.outcome.value}"),
            )

        return SkillExecuteResponse(
            correlation=request.correlation,
            outcome=SkillOutcome.HANDLED,
            text="Fatto." if language == "it" else "Done.",
            result={
                "operation": operation.value,
                "resource_type": target.resource_type.value,
                "resource_id": target.resource_id,
                "reference": reference_text,
            },
        )
