from __future__ import annotations

from shared.protocol.capabilities import ResolveCardinality

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
        "cardinality": "ONE",
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
    # Deterministic named-resource lookup is read-only before LLM fallback.
    assert len(capability.resolve_calls) == 1
    assert capability.resolve_calls[0][0].reference == "what is the weather tomorrow"
    assert capability.resolve_calls[0][0].resource_type is None
    assert capability.resolve_calls[0][0].cardinality is ResolveCardinality.MANY
    assert capability.execute_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("language,text", [("it", "accendi la luce sconosciuta"), ("en", "turn on the unknown light")])
async def test_missing_target_asks_for_details_without_executing(language, text):
    class Missing(FakeCapability):
        async def resolve(self, reference, trusted_context, *, correlation):
            return ResolveResponse(correlation=correlation, status=ResolveStatus.NOT_FOUND, reference=reference)
    capability = Missing()
    skill = HomeAssistantActionSkill(capability)
    check = skill_request(text, language)
    response = await skill.execute(SkillExecuteRequest(correlation=check.correlation, match=skill.match(check), text=text, language=language, context=check.context))
    assert response.outcome is SkillOutcome.NEEDS_CLARIFICATION
    assert response.text and "?" in response.text
    assert response.pending_state["llm_clarification"]["operation"] == "TURN_ON"
    assert response.pending_state["llm_clarification"]["reference"]
    assert capability.execute_calls == []


@pytest.mark.asyncio
async def test_missing_light_followup_preserves_operation_and_cannot_trigger_same_named_scene():
    class Collision(FakeCapability):
        async def resolve(self, reference, trusted_context, *, correlation):
            self.resolve_calls.append((reference, trusted_context, correlation))
            resources = []
            if reference.reference.casefold() == "kitchen":
                resources = [("light.kitchen", NyraResourceType.LIGHT)] if reference.resource_type is NyraResourceType.LIGHT else [("scene.kitchen", NyraResourceType.SCENE)]
            return ResolveResponse(correlation=correlation, status=ResolveStatus.RESOLVED if resources else ResolveStatus.NOT_FOUND, reference=reference, candidates=[ResolveCandidate(resource=ResolvedResource(resource_id=entity, resource_type=kind, name="Kitchen")) for entity, kind in resources])
    capability = Collision()
    skill = HomeAssistantActionSkill(capability)
    first = skill_request("turn off the unknown light")
    result = await skill.execute(SkillExecuteRequest(correlation=first.correlation, match=skill.match(first), text=first.text, language="en", context=first.context))
    reply = skill_request("Kitchen").model_copy(update={"pending_state": result.pending_state})
    if skill.matches(reply):
        match = skill.match(reply)
    else:
        match = await skill.fast_path_match(reply)
    await skill.execute(SkillExecuteRequest(correlation=reply.correlation, match=match, text=reply.text, language="en", context=reply.context, pending_state=result.pending_state))
    assert capability.execute_calls[0][0].resource_id == "light.kitchen"
    assert capability.execute_calls[0][0].operation is NyraOperation.TURN_OFF


@pytest.mark.asyncio
@pytest.mark.parametrize("language,text", [("it", "Spegni, pompa piscina."), ("it", "Spegni la pompa della piscina"), ("en", "Turn off the pool pump")])
async def test_pump_commands_resolve_and_execute_off_instead_of_returning_a_state_report(language, text):
    class Pump(FakeCapability):
        async def resolve(self, reference, trusted_context, *, correlation):
            self.resolve_calls.append((reference, trusted_context, correlation))
            expected = "pompa piscina" if language == "it" else "pool pump"
            assert reference.reference == expected
            assert reference.resource_type is NyraResourceType.SWITCH
            return ResolveResponse(correlation=correlation, status=ResolveStatus.RESOLVED, reference=reference, candidates=[ResolveCandidate(resource=ResolvedResource(resource_id="switch.pool_pump", resource_type=NyraResourceType.SWITCH, name="Pool pump"))])
    capability = Pump()
    skill = HomeAssistantActionSkill(capability)
    check = skill_request(text, language)
    assert skill.matches(check)
    response = await skill.execute(SkillExecuteRequest(correlation=check.correlation, match=skill.match(check), text=text, language=language, context=check.context))
    assert response.outcome is SkillOutcome.HANDLED
    assert capability.execute_calls[0][0].operation is NyraOperation.TURN_OFF
    assert capability.execute_calls[0][0].resource_id == "switch.pool_pump"


@pytest.mark.asyncio
async def test_reference_cleanup_preserves_numbered_device_name():
    class Named(FakeCapability):
        async def resolve(self, reference, trusted_context, *, correlation):
            assert reference.reference == "light one"
            return await super().resolve(reference, trusted_context, correlation=correlation)
    capability = Named()
    skill = HomeAssistantActionSkill(capability)
    check = skill_request("turn off light one")
    await skill.execute(SkillExecuteRequest(correlation=check.correlation, match=skill.match(check), text=check.text, language=check.language, context=check.context))
