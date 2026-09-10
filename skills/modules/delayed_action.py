from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from shared.protocol.capabilities import (
    CapabilityCorrelation,
    ExecuteRequest,
    ResolveCardinality,
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
from skills.modules.home_assistant import parse_command


@dataclass(frozen=True)
class ParsedDelayedAction:
    initial_operation: NyraOperation
    followup_operation: NyraOperation
    resource_type: NyraResourceType
    reference: str
    delay_seconds: float


_DELAY_PATTERNS = {
    "en": re.compile(
        r"^(?P<first>.+?)\s+and\s+(?P<followup>.+?)\s+after\s+"
        r"(?P<amount>\d+(?:\.\d+)?)\s+"
        r"(?P<unit>seconds?|minutes?|hours?)$",
        re.IGNORECASE,
    ),
    "it": re.compile(
        r"^(?P<first>.+?)\s+e\s+(?P<followup>.+?)\s+dopo\s+"
        r"(?P<amount>\d+(?:[.,]\d+)?)\s+"
        r"(?P<unit>second[oi]|minut[oi]|or[ae])$",
        re.IGNORECASE,
    ),
}

_FOLLOWUPS = {
    "en": {
        "turn it off": NyraOperation.TURN_OFF,
        "turn it on": NyraOperation.TURN_ON,
        "open it": NyraOperation.OPEN,
        "close it": NyraOperation.CLOSE,
    },
    "it": {
        "spegnila": NyraOperation.TURN_OFF,
        "spegnilo": NyraOperation.TURN_OFF,
        "accendila": NyraOperation.TURN_ON,
        "accendilo": NyraOperation.TURN_ON,
        "aprila": NyraOperation.OPEN,
        "aprilo": NyraOperation.OPEN,
        "chiudila": NyraOperation.CLOSE,
        "chiudilo": NyraOperation.CLOSE,
    },
}

_INVERSE = {
    NyraOperation.TURN_ON: NyraOperation.TURN_OFF,
    NyraOperation.TURN_OFF: NyraOperation.TURN_ON,
    NyraOperation.OPEN: NyraOperation.CLOSE,
    NyraOperation.CLOSE: NyraOperation.OPEN,
}


def _language(value: str) -> str:
    return "it" if value.split("-", 1)[0].lower() == "it" else "en"


def _seconds(amount: str, unit: str) -> float:
    value = float(amount.replace(",", "."))
    unit = unit.casefold()
    if unit.startswith("minute") or unit.startswith("minut"):
        return value * 60.0
    if unit.startswith("hour") or unit.startswith("or"):
        return value * 3600.0
    return value


def parse_delayed_action(text: str, language: str) -> ParsedDelayedAction | None:
    selected = _language(language)
    match = _DELAY_PATTERNS[selected].fullmatch(" ".join(text.split()))
    if match is None:
        return None

    initial = parse_command(match.group("first"), selected)
    if initial is None:
        return None

    followup_text = " ".join(match.group("followup").casefold().split())
    followup = _FOLLOWUPS[selected].get(followup_text)
    if followup is None:
        explicit = parse_command(match.group("followup"), selected)
        if explicit is None:
            return None
        if (
            explicit.reference != initial.reference
            or explicit.resource_type is not initial.resource_type
        ):
            return None
        followup = explicit.operation

    if _INVERSE.get(initial.operation) is not followup:
        return None

    delay = _seconds(match.group("amount"), match.group("unit"))
    if delay <= 0:
        return None

    return ParsedDelayedAction(
        initial_operation=initial.operation,
        followup_operation=followup,
        resource_type=initial.resource_type,
        reference=initial.reference,
        delay_seconds=delay,
    )


class DelayedActionSkill:
    name = "delayed_action"
    priority = 105

    def __init__(self, capability: Any, scheduler: Any) -> None:
        self.capability = capability
        self.scheduler = scheduler

    def matches(self, request: SkillCheckRequest) -> bool:
        return parse_delayed_action(request.text, request.language) is not None

    def match(self, request: SkillCheckRequest) -> SkillMatch:
        parsed = parse_delayed_action(request.text, request.language)
        if parsed is None:
            return SkillMatch(matched=False)
        return SkillMatch(
            matched=True,
            skill_name=self.name,
            token=self.name,
            memory_requirement=MemoryRequirement.NONE,
            metadata={
                "initial_operation": parsed.initial_operation.value,
                "followup_operation": parsed.followup_operation.value,
                "resource_type": parsed.resource_type.value,
                "reference": parsed.reference,
                "delay_seconds": parsed.delay_seconds,
            },
        )

    async def execute(
        self,
        request: SkillExecuteRequest,
    ) -> SkillExecuteResponse:
        metadata = request.match.metadata
        try:
            initial_operation = NyraOperation(metadata["initial_operation"])
            followup_operation = NyraOperation(metadata["followup_operation"])
            resource_type = NyraResourceType(metadata["resource_type"])
            reference = str(metadata["reference"])
            delay_seconds = float(metadata["delay_seconds"])
        except (KeyError, TypeError, ValueError):
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code="INVALID_DELAYED_ACTION_MATCH"),
            )

        if (
            _INVERSE.get(initial_operation) is not followup_operation
            or delay_seconds <= 0
        ):
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code="INVALID_DELAYED_ACTION_MATCH"),
            )

        capability_correlation = CapabilityCorrelation(
            **request.correlation.model_dump()
        )
        trusted_context = dict(request.context)
        resolved = await self.capability.resolve(
            ResourceReference(
                reference=reference,
                resource_type=resource_type,
                cardinality=ResolveCardinality.ONE,
            ),
            trusted_context,
            correlation=capability_correlation,
        )
        if (
            resolved.status is not ResolveStatus.RESOLVED
            or len(resolved.candidates) != 1
        ):
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code=f"HA_TARGET_{resolved.status.value}"),
            )

        target = resolved.candidates[0].resource
        immediate = await self.capability.execute(
            ExecuteRequest(
                correlation=capability_correlation,
                operation=initial_operation,
                resource_id=target.resource_id,
                resource_type=target.resource_type,
            ),
            trusted_context,
        )
        if immediate.outcome is not CommonOutcome.SUCCESS:
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=immediate.error
                or ErrorDetail(code=f"HA_{immediate.outcome.value}"),
            )

        origin_request_id = (
            request.correlation.origin_request_id
            or request.correlation.request_id
        )
        if origin_request_id is None:
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code="MISSING_ORIGIN_REQUEST_ID"),
            )

        execute_at = datetime.now(timezone.utc) + timedelta(
            seconds=delay_seconds
        )
        job = self.scheduler.schedule_action(
            execute_at=execute_at,
            origin_request_id=origin_request_id,
            created_trace_id=request.correlation.trace_id,
            operation=followup_operation,
            resource_id=target.resource_id,
            resource_type=target.resource_type,
            trusted_context=trusted_context,
        )

        language = _language(request.language)
        return SkillExecuteResponse(
            correlation=request.correlation,
            outcome=SkillOutcome.HANDLED,
            text=(
                "Fatto. Eseguirò automaticamente l'azione successiva."
                if language == "it"
                else "Done. I will perform the follow-up automatically."
            ),
            result={
                "job_id": job.job_id,
                "job_status": job.status.value,
                "execute_at": job.execute_at.isoformat(),
                "resource_id": target.resource_id,
                "initial_operation": initial_operation.value,
                "followup_operation": followup_operation.value,
            },
        )
