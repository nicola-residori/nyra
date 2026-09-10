from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any, Callable
from uuid import uuid4

from shared.protocol.behavior import (
    Behavior,
    BehaviorAction,
    BehaviorActionType,
    BehaviorLifecycle,
    BehaviorTrigger,
)
from shared.protocol.capabilities import AutomationCreateRequest, CapabilityCorrelation
from shared.protocol.common import CommonOutcome, ErrorDetail
from shared.protocol.execution_common import ExecutionStep
from shared.protocol.memory import MemoryRequirement
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillExecuteRequest,
    SkillExecuteResponse,
    SkillMatch,
    SkillOutcome,
)
from skills.modules.home_assistant import parse_command


_TIME = r"(?P<hour>\d{1,2}):(?P<minute>\d{2})"


def _language(value: str) -> str:
    return "it" if value.split("-", 1)[0].lower() == "it" else "en"


def _parse_time(hour: str, minute: str) -> tuple[int, int] | None:
    h = int(hour)
    m = int(minute)
    if h not in range(24) or m not in range(60):
        return None
    return h, m


def _behavior_action(command) -> BehaviorAction:
    return BehaviorAction(
        type=BehaviorActionType.ACTION,
        action=ExecutionStep(
            step_id="action_1",
            operation=command.operation,
            target={
                "reference": command.reference,
                "resource_type": command.resource_type,
            },
        ),
    )


def parse_behavior(
    text: str,
    language: str,
    *,
    now: datetime | None = None,
) -> Behavior | None:
    language = _language(language)
    cleaned = " ".join(text.strip().split())
    current = now or datetime.now(timezone.utc)

    if language == "en":
        patterns = (
            (
                re.compile(rf"^tomorrow at {_TIME} (?P<command>.+)$", re.I),
                "one_shot",
            ),
            (
                re.compile(rf"^(?P<command>.+) every day at {_TIME}$", re.I),
                "daily",
            ),
            (
                re.compile(r"^(?P<command>.+) every day at sunset$", re.I),
                "sunset",
            ),
            (
                re.compile(
                    r"^when event (?P<event>[a-zA-Z0-9_.:-]+) occurs,? (?P<command>.+)$",
                    re.I,
                ),
                "event",
            ),
        )
    else:
        patterns = (
            (
                re.compile(rf"^domani alle {_TIME} (?P<command>.+)$", re.I),
                "one_shot",
            ),
            (
                re.compile(rf"^(?P<command>.+) ogni giorno alle {_TIME}$", re.I),
                "daily",
            ),
            (
                re.compile(r"^(?P<command>.+) ogni giorno al tramonto$", re.I),
                "sunset",
            ),
            (
                re.compile(
                    r"^quando avviene l evento (?P<event>[a-zA-Z0-9_.:-]+),? (?P<command>.+)$",
                    re.I,
                ),
                "event",
            ),
        )

    for pattern, kind in patterns:
        match = pattern.fullmatch(cleaned)
        if match is None:
            continue

        command = parse_command(match.group("command"), language)
        if command is None:
            return None

        lifecycle = (
            BehaviorLifecycle.ONE_SHOT
            if kind == "one_shot"
            else BehaviorLifecycle.PERSISTENT
        )
        if kind == "one_shot":
            parsed_time = _parse_time(match.group("hour"), match.group("minute"))
            if parsed_time is None:
                return None
            hour, minute = parsed_time
            target = (current + timedelta(days=1)).astimezone(current.tzinfo)
            target = target.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0,
            )
            trigger = BehaviorTrigger(
                kind="time",
                expression=target.isoformat(),
            )
        elif kind == "daily":
            parsed_time = _parse_time(match.group("hour"), match.group("minute"))
            if parsed_time is None:
                return None
            hour, minute = parsed_time
            trigger = BehaviorTrigger(
                kind="time",
                expression=f"{hour:02d}:{minute:02d}:00",
            )
        elif kind == "sunset":
            trigger = BehaviorTrigger(kind="sun", expression="sunset")
        else:
            trigger = BehaviorTrigger(
                kind="event",
                expression=match.group("event"),
            )

        return Behavior(
            behavior_id=f"beh_{uuid4()}",
            lifecycle=lifecycle,
            triggers=[trigger],
            actions=[_behavior_action(command)],
        )

    return None


class BehaviorSkill:
    name = "behavior"
    priority = 95

    def __init__(
        self,
        capability: Any,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.capability = capability
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def matches(self, request: SkillCheckRequest) -> bool:
        return parse_behavior(
            request.text,
            request.language,
            now=self.clock(),
        ) is not None

    def match(self, request: SkillCheckRequest) -> SkillMatch:
        behavior = parse_behavior(
            request.text,
            request.language,
            now=self.clock(),
        )
        if behavior is None:
            return SkillMatch(matched=False)
        return SkillMatch(
            matched=True,
            skill_name=self.name,
            token=self.name,
            memory_requirement=MemoryRequirement.NONE,
            metadata={
                "behavior": behavior.model_dump(mode="json"),
            },
        )

    async def execute(
        self,
        request: SkillExecuteRequest,
    ) -> SkillExecuteResponse:
        try:
            behavior = Behavior.model_validate(
                request.match.metadata["behavior"]
            )
        except (KeyError, TypeError, ValueError):
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code="INVALID_BEHAVIOR_MATCH"),
            )

        response = await self.capability.automation_create(
            AutomationCreateRequest(
                correlation=CapabilityCorrelation(
                    **request.correlation.model_dump()
                ),
                behavior=behavior,
            ),
            dict(request.context),
        )

        if response.outcome is CommonOutcome.AMBIGUOUS:
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.NEEDS_CLARIFICATION,
                text=(
                    "Esiste già un'automazione simile. Vuoi crearne comunque una nuova?"
                    if _language(request.language) == "it"
                    else "A similar automation already exists. Do you want to create another one?"
                ),
                pending_state={
                    "kind": "behavior_duplicate",
                    "behavior": behavior.model_dump(mode="json"),
                },
            )

        if response.outcome is not CommonOutcome.SUCCESS:
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=response.error
                or ErrorDetail(code=f"HA_AUTOMATION_{response.outcome.value}"),
            )

        return SkillExecuteResponse(
            correlation=request.correlation,
            outcome=SkillOutcome.HANDLED,
            text=(
                "Automazione creata."
                if _language(request.language) == "it"
                else "Automation created."
            ),
            result={
                "automation_id": response.automation_id,
                "behavior_id": behavior.behavior_id,
                "lifecycle": behavior.lifecycle.value,
            },
        )
