from __future__ import annotations

import pytest

from shared.protocol.capabilities import (
    ExecuteResponse,
    ResolveCandidate,
    ResolveResponse,
    ResolveStatus,
    ResolvedResource,
)
from shared.protocol.common import CommonOutcome
from shared.protocol.execution_common import NyraResourceType
from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCorrelation,
    SkillExecuteRequest,
    SkillOutcome,
)
from skills.modules.home_assistant import HomeAssistantActionSkill, parse_command


class FakeCapability:
    def __init__(self, resources):
        self.resources = resources
        self.resolve_calls = []
        self.execute_calls = []

    async def resolve(self, reference, trusted_context, *, correlation):
        self.resolve_calls.append((reference, trusted_context))
        return ResolveResponse(
            correlation=correlation,
            status=ResolveStatus.RESOLVED if self.resources else ResolveStatus.NOT_FOUND,
            reference=reference,
            candidates=[ResolveCandidate(resource=r) for r in self.resources],
        )

    async def execute(self, request, trusted_context):
        self.execute_calls.append((request, trusted_context))
        return ExecuteResponse(
            correlation=request.correlation,
            outcome=CommonOutcome.SUCCESS,
        )


def request(text: str, context: dict) -> SkillCheckRequest:
    return SkillCheckRequest(
        correlation=SkillCorrelation(
            request_id=new_request_id(),
            trace_id=new_trace_id(),
        ),
        text=text,
        language="it",
        context=context,
    )


@pytest.mark.parametrize(
    ("text", "rtype", "many"),
    [
        ("accendi la luce", NyraResourceType.LIGHT, False),
        ("accendi le luci", NyraResourceType.LIGHT, True),
        ("spegni le lampade", NyraResourceType.LIGHT, True),
        ("apri le tapparelle", NyraResourceType.COVER, True),
        ("chiudi le tende", NyraResourceType.COVER, True),
        ("accendi gli interruttori", NyraResourceType.SWITCH, True),
    ],
)
def test_italian_singular_plural_are_deterministic(text, rtype, many):
    parsed = parse_command(text, "it")
    assert parsed is not None
    assert parsed.resource_type is rtype
    assert parsed.many is many


@pytest.mark.asyncio
async def test_implicit_area_scopes_singular_to_speaker_area():
    cap = FakeCapability([
        ResolvedResource(
            resource_id="light.kitchen",
            resource_type=NyraResourceType.LIGHT,
            name="Luce cucina",
        )
    ])
    skill = HomeAssistantActionSkill(cap)
    req = request("accendi la luce", {"area": "cucina"})
    match = skill.match(req)

    out = await skill.execute(
        SkillExecuteRequest(
            correlation=req.correlation,
            match=match,
            text=req.text,
            language=req.language,
            context=req.context,
        )
    )

    ref, _ = cap.resolve_calls[0]
    assert ref.reference == "luce"
    assert ref.cardinality.value == "ONE"
    assert out.outcome is SkillOutcome.HANDLED
    assert len(cap.execute_calls) == 1


@pytest.mark.asyncio
async def test_explicit_area_overrides_speaker_area():
    cap = FakeCapability([
        ResolvedResource(
            resource_id="light.living",
            resource_type=NyraResourceType.LIGHT,
            name="Luce soggiorno",
        )
    ])
    skill = HomeAssistantActionSkill(cap)
    req = request("accendi la luce soggiorno", {"area": "cucina"})
    match = skill.match(req)

    await skill.execute(
        SkillExecuteRequest(
            correlation=req.correlation,
            match=match,
            text=req.text,
            language=req.language,
            context=req.context,
        )
    )

    assert cap.resolve_calls[0][0].reference == "luce soggiorno"
    assert cap.resolve_calls[0][1]["area"] == "cucina"


@pytest.mark.asyncio
async def test_plural_executes_all_matches_in_speaker_area():
    resources = [
        ResolvedResource(
            resource_id="light.kitchen_main",
            resource_type=NyraResourceType.LIGHT,
            name="Luce cucina principale",
        ),
        ResolvedResource(
            resource_id="light.kitchen_island",
            resource_type=NyraResourceType.LIGHT,
            name="Luce cucina isola",
        ),
    ]
    cap = FakeCapability(resources)
    skill = HomeAssistantActionSkill(cap)
    req = request("accendi le luci", {"area": "cucina"})
    match = skill.match(req)

    out = await skill.execute(
        SkillExecuteRequest(
            correlation=req.correlation,
            match=match,
            text=req.text,
            language=req.language,
            context=req.context,
        )
    )

    ref, _ = cap.resolve_calls[0]
    assert ref.reference == "luce"
    assert ref.cardinality.value == "MANY"
    assert [x[0].resource_id for x in cap.execute_calls] == [
        "light.kitchen_main",
        "light.kitchen_island",
    ]
    assert out.outcome is SkillOutcome.HANDLED


@pytest.mark.asyncio
async def test_plural_explicit_area_executes_all_there():
    resources = [
        ResolvedResource(
            resource_id="light.living_a",
            resource_type=NyraResourceType.LIGHT,
            name="Luce soggiorno A",
        ),
        ResolvedResource(
            resource_id="light.living_b",
            resource_type=NyraResourceType.LIGHT,
            name="Luce soggiorno B",
        ),
    ]
    cap = FakeCapability(resources)
    skill = HomeAssistantActionSkill(cap)
    req = request("accendi le luci soggiorno", {"area": "cucina"})
    match = skill.match(req)

    await skill.execute(
        SkillExecuteRequest(
            correlation=req.correlation,
            match=match,
            text=req.text,
            language=req.language,
            context=req.context,
        )
    )

    assert cap.resolve_calls[0][0].reference == "luce"
    assert cap.resolve_calls[0][1]["area"] == "soggiorno"
    assert len(cap.execute_calls) == 2

def test_parse_explicit_area_is_extracted():
    parsed = parse_command("accendi luci soggiorno", "it-IT")
    assert parsed is not None
    assert parsed.resource_type is NyraResourceType.LIGHT
    assert parsed.many is True
    assert parsed.area == "soggiorno"

def test_parse_explicit_other_area_is_extracted():
    parsed = parse_command("spegni le luci cucina", "it-IT")
    assert parsed is not None
    assert parsed.area == "cucina"
