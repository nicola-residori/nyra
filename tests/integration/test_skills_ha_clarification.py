from __future__ import annotations

import pytest

from router.app import _RemoteSkillPort
from shared.protocol.capabilities import (
    ExecuteResponse,
    ResolveCandidate,
    ResolveResponse,
    ResolveStatus,
    ResolvedResource,
)
from shared.protocol.common import CommonOutcome
from shared.protocol.execution_common import NyraResourceType
from shared.protocol.requests import RequestStatus
from skills.modules.home_assistant import HomeAssistantActionSkill
from skills.registry import SkillDefinition, SkillRegistry
from skills.service import SkillsService
from tests.router.test_request_lifecycle import LlmPort, request, service


class AmbiguousCapability:
    def __init__(self):
        self.resolve_calls = 0
        self.execute_calls = []

    async def resolve(self, reference, trusted_context, *, correlation):
        self.resolve_calls += 1
        return ResolveResponse(
            correlation=correlation,
            status=ResolveStatus.AMBIGUOUS,
            reference=reference,
            candidates=[
                ResolveCandidate(
                    resource=ResolvedResource(
                        resource_id="light.desk",
                        resource_type=NyraResourceType.LIGHT,
                        name="Lampada Scrivania",
                    ),
                    score=1.0,
                ),
                ResolveCandidate(
                    resource=ResolvedResource(
                        resource_id="light.bedside",
                        resource_type=NyraResourceType.LIGHT,
                        name="Lampada Comodino",
                    ),
                    score=1.0,
                ),
            ],
        )

    async def execute(self, request, trusted_context):
        self.execute_calls.append(request)
        return ExecuteResponse(
            correlation=request.correlation,
            outcome=CommonOutcome.SUCCESS,
        )


class BridgeSkillsClient:
    def __init__(self, skills_service):
        self.skills_service = skills_service

    async def check(self, payload):
        return await self.skills_service.check(payload)

    async def execute(self, payload):
        return await self.skills_service.execute(payload)


def remote_port(capability):
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
    return _RemoteSkillPort(
        BridgeSkillsClient(SkillsService(registry=registry))
    )


def trusted_identity():
    return {
        "user_id": "user-a",
        "provider": "home_assistant",
        "confidence": 1.0,
    }


@pytest.mark.asyncio
async def test_ambiguous_target_round_trip_persists_router_state_and_executes_once(
    tmp_path,
):
    capability = AmbiguousCapability()
    llm = LlmPort()
    lifecycle, store, _ = service(
        tmp_path,
        skill_port=remote_port(capability),
        llm_port=llm,
    )
    first_request = request(
        kind="ha_assist",
        identity=trusted_identity(),
        text="accendi la lampada",
    )

    first = await lifecycle.execute(first_request)

    assert first.status is RequestStatus.NEEDS_CLARIFICATION
    assert first.request_id == first_request.request_id
    assert first.session_id == first_request.session_id
    assert first.response is not None
    assert "Lampada Scrivania" in first.response.text
    assert "Lampada Comodino" in first.response.text
    assert "light.desk" not in first.response.text
    assert "light.bedside" not in first.response.text
    assert llm.calls == 0
    assert capability.execute_calls == []

    stored = store.get(first_request.request_id)
    assert stored.pending_state["kind"] == "ha_target_clarification"
    first_trace = first.trace_id

    second = await lifecycle.execute(
        request(
            request_id=first_request.request_id,
            session_id=first_request.session_id,
            kind="ha_assist",
            identity=trusted_identity(),
            text="quella della scrivania",
        )
    )

    assert second.status is RequestStatus.COMPLETED
    assert second.request_id == first_request.request_id
    assert second.session_id == first_request.session_id
    assert second.trace_id != first_trace
    assert llm.calls == 0
    assert capability.resolve_calls == 1
    assert len(capability.execute_calls) == 1
    assert capability.execute_calls[0].resource_id == "light.desk"


@pytest.mark.asyncio
async def test_unrelated_followup_does_not_execute_stale_target(tmp_path):
    capability = AmbiguousCapability()
    llm = LlmPort()
    lifecycle, _, _ = service(
        tmp_path,
        skill_port=remote_port(capability),
        llm_port=llm,
    )
    first_request = request(
        kind="ha_assist",
        identity=trusted_identity(),
        text="accendi la lampada",
    )
    first = await lifecycle.execute(first_request)
    assert first.status is RequestStatus.NEEDS_CLARIFICATION

    second = await lifecycle.execute(
        request(
            request_id=first_request.request_id,
            session_id=first_request.session_id,
            kind="ha_assist",
            identity=trusted_identity(),
            text="che tempo fa domani",
        )
    )

    assert second.status is RequestStatus.COMPLETED
    assert llm.calls == 1
    assert capability.execute_calls == []


@pytest.mark.asyncio
async def test_no_candidate_stays_non_fallback_failed(tmp_path):
    class MissingCapability(AmbiguousCapability):
        async def resolve(self, reference, trusted_context, *, correlation):
            self.resolve_calls += 1
            return ResolveResponse(
                correlation=correlation,
                status=ResolveStatus.NOT_FOUND,
                reference=reference,
                candidates=[],
            )

    capability = MissingCapability()
    llm = LlmPort()
    lifecycle, _, _ = service(
        tmp_path,
        skill_port=remote_port(capability),
        llm_port=llm,
    )

    result = await lifecycle.execute(
        request(
            kind="ha_assist",
            identity=trusted_identity(),
            text="accendi la lampada",
        )
    )

    assert result.status is RequestStatus.FAILED
    assert llm.calls == 0
    assert capability.execute_calls == []
