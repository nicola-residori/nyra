from datetime import datetime, timezone

import pytest

from shared.protocol.capabilities import AutomationCreateResponse
from shared.protocol.common import CommonOutcome
from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCorrelation,
    SkillExecuteRequest,
    SkillOutcome,
)
NOW = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)


class Capability:
    def __init__(self, outcome=CommonOutcome.SUCCESS):
        self.outcome = outcome
        self.calls = []

    async def automation_create(self, request, trusted_context):
        self.calls.append((request, trusted_context))
        return AutomationCreateResponse(
            correlation=request.correlation,
            outcome=self.outcome,
            automation_id="nyra_test" if self.outcome is CommonOutcome.SUCCESS else None,
            behavior=request.behavior if self.outcome is CommonOutcome.SUCCESS else None,
        )


def correlation():
    request_id = new_request_id()
    return SkillCorrelation(
        request_id=request_id,
        origin_request_id=request_id,
        trace_id=new_trace_id(),
    )


def test_one_shot_future_action_becomes_behavior():
    from skills.modules.behavior import parse_behavior
    behavior = parse_behavior(
        "tomorrow at 07:30 turn on the kitchen light",
        "en",
        now=NOW,
    )
    assert behavior is not None
    assert behavior.lifecycle.value == "ONE_SHOT"
    assert behavior.triggers[0].kind == "time"
    assert behavior.triggers[0].expression.startswith("2026-09-11T07:30:00")


def test_recurring_and_event_driven_requests_become_persistent_behaviors():
    from skills.modules.behavior import parse_behavior
    daily = parse_behavior(
        "turn on the kitchen light every day at 07:30",
        "en",
        now=NOW,
    )
    event = parse_behavior(
        "when event front_door_open occurs, turn on the hall light",
        "en",
        now=NOW,
    )

    assert daily is not None
    assert daily.lifecycle.value == "PERSISTENT"
    assert daily.triggers[0].kind == "time"

    assert event is not None
    assert event.lifecycle.value == "PERSISTENT"
    assert event.triggers[0].kind == "event"
    assert event.triggers[0].expression == "front_door_open"


def test_short_delayed_interaction_is_not_behavior_even_with_long_delay():
    from skills.modules.behavior import parse_behavior
    assert parse_behavior(
        "turn on the kitchen light and turn it off after 2 hours",
        "en",
        now=NOW,
    ) is None


@pytest.mark.asyncio
async def test_behavior_skill_materializes_only_through_router_capability():
    from skills.modules.behavior import BehaviorSkill
    capability = Capability()
    skill = BehaviorSkill(capability, clock=lambda: NOW)
    corr = correlation()
    check = SkillCheckRequest(
        correlation=corr,
        text="turn on the kitchen light every day at 07:30",
        language="en",
        context={"allowed_resource_ids": ["light.kitchen"]},
    )

    match = skill.match(check)
    response = await skill.execute(
        SkillExecuteRequest(
            correlation=corr,
            match=match,
            text=check.text,
            language=check.language,
            context=check.context,
        )
    )

    assert response.outcome is SkillOutcome.HANDLED
    assert response.result["automation_id"] == "nyra_test"
    assert len(capability.calls) == 1
    assert capability.calls[0][1] == check.context


@pytest.mark.asyncio
async def test_probable_equivalent_returns_needs_clarification():
    from skills.modules.behavior import BehaviorSkill
    capability = Capability(CommonOutcome.AMBIGUOUS)
    skill = BehaviorSkill(capability, clock=lambda: NOW)
    corr = correlation()
    check = SkillCheckRequest(
        correlation=corr,
        text="turn on the kitchen light every day at 07:30",
        language="en",
        context={},
    )
    response = await skill.execute(
        SkillExecuteRequest(
            correlation=corr,
            match=skill.match(check),
            text=check.text,
            language=check.language,
            context={},
        )
    )
    assert response.outcome is SkillOutcome.NEEDS_CLARIFICATION
    assert response.pending_state["kind"] == "behavior_duplicate"
