from __future__ import annotations

import pytest

from shared.protocol.capabilities import (
    CapabilityCorrelation,
    ExecuteResponse,
    ResolveCandidate,
    ResolveResponse,
    ResolveStatus,
    ResolvedResource,
)
from shared.protocol.common import CommonOutcome
from shared.protocol.execution_common import NyraOperation, NyraResourceType
from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCorrelation,
    SkillExecuteRequest,
    SkillOutcome,
)
from skills.modules.home_assistant import HomeAssistantActionSkill
from skills.registry import SkillDefinition, SkillRegistry
from skills.service import SkillsService


class FakeCapability:
    def __init__(self):
        self.resolve_calls = []
        self.execute_calls = []

    async def resolve(self, reference, trusted_context, *, correlation):
        self.resolve_calls.append((reference, trusted_context, correlation))
        return ResolveResponse(
            correlation=correlation,
            status=ResolveStatus.RESOLVED,
            reference=reference,
            candidates=[
                ResolveCandidate(
                    resource=ResolvedResource(
                        resource_id="light.kitchen",
                        resource_type=NyraResourceType.LIGHT,
                        name="Kitchen Light",
                    )
                )
            ],
        )

    async def execute(self, request, trusted_context):
        self.execute_calls.append((request, trusted_context))
        return ExecuteResponse(
            correlation=request.correlation,
            outcome=CommonOutcome.SUCCESS,
        )


def skill_request(text: str, language: str = "en") -> SkillCheckRequest:
    return SkillCheckRequest(
        correlation=SkillCorrelation(
            request_id=new_request_id(),
            trace_id=new_trace_id(),
        ),
        text=text,
        language=language,
        context={"allowed_resource_ids": ["light.kitchen"]},
    )


@pytest.mark.parametrize(
    ("text", "language", "operation", "resource_type", "reference"),
    [
        ("turn on the kitchen light", "en", "TURN_ON", "LIGHT", "kitchen light"),
        ("turn off the kitchen light", "en", "TURN_OFF", "LIGHT", "kitchen light"),
        ("open the bedroom blind", "en", "OPEN", "COVER", "bedroom blind"),
        ("close the bedroom blind", "en", "CLOSE", "COVER", "bedroom blind"),
        ("accendi la luce cucina", "it", "TURN_ON", "LIGHT", "luce cucina"),
        ("spegni la lampada studio", "it", "TURN_OFF", "LIGHT", "lampada studio"),
        ("apri la tenda camera", "it", "OPEN", "COVER", "tenda camera"),
        ("chiudi la tapparella camera", "it", "CLOSE", "COVER", "tapparella camera"),
    ],
)
def test_match_is_deterministic_and_language_aware(
    text,
    language,
    operation,
    resource_type,
    reference,
):
    skill = HomeAssistantActionSkill(FakeCapability())
    request = skill_request(text, language)

    assert skill.matches(request) is True
    match = skill.match(request)

    assert match.metadata == {
        "operation": operation,
        "resource_type": resource_type,
        "reference": reference,
    }


@pytest.mark.asyncio
async def test_skill_resolves_semantic_reference_then_executes_resolved_target():
    capability = FakeCapability()
    skill = HomeAssistantActionSkill(capability)
    check = skill_request("turn on the kitchen light")
    match = skill.match(check)

    response = await skill.execute(
        SkillExecuteRequest(
            correlation=check.correlation,
            match=match,
            text=check.text,
            language=check.language,
            context=check.context,
        )
    )

    assert response.outcome is SkillOutcome.HANDLED
    assert response.text == "Done."
    assert len(capability.resolve_calls) == 1
    reference, trusted_context, _ = capability.resolve_calls[0]
    assert reference.reference == "kitchen light"
    assert reference.resource_type is NyraResourceType.LIGHT
    assert trusted_context == check.context

    assert len(capability.execute_calls) == 1
    execute_request, execute_context = capability.execute_calls[0]
    assert execute_request.operation is NyraOperation.TURN_ON
    assert execute_request.resource_id == "light.kitchen"
    assert execute_context == check.context


@pytest.mark.asyncio
async def test_unrelated_question_is_miss_not_failed():
    capability = FakeCapability()
    skill = HomeAssistantActionSkill(capability)
    registry = SkillRegistry()
    registry.register(
        SkillDefinition(
            name=skill.name,
            priority=skill.priority,
            matcher=skill.matches,
            executor=skill.execute,
        )
    )
    service = SkillsService(registry=registry)
    request = skill_request("what is the weather tomorrow?")

    response = await service.check(request)

    assert response.outcome is SkillOutcome.MISS
    assert response.error is None
    assert capability.resolve_calls == []
    assert capability.execute_calls == []
