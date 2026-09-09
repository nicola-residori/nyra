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


def _language(value: str) -> str:
    language = value.split("-", 1)[0].lower()
    return language if language in _ACTIONS else "en"


def _normalized(value: str) -> str:
    return " ".join(
        re.sub(r"[^\w]+", " ", value.casefold()).split()
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
        return parse_command(request.text, request.language) is not None

    def match(self, request: SkillCheckRequest) -> SkillMatch:
        parsed = parse_command(request.text, request.language)
        if parsed is None:
            return SkillMatch(matched=False)

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
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code="HA_TARGET_AMBIGUOUS"),
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

        language = _language(request.language)
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
