from __future__ import annotations

import pytest

from router.app import _RemoteSkillPort
from router.lifecycle.service import ContextResult, LifecycleDecision, SkillMatch
from router.skills_client import SkillsUnavailable
from shared.protocol.ids import new_trace_id
from shared.protocol.requests import RequestStatus
from shared.protocol.skills import SkillOutcome
from tests.router.test_request_lifecycle import LlmPort, request, service


class OutcomeSkillPort:
    def __init__(self, outcome: SkillOutcome):
        self.outcome = outcome
        self.executed = 0

    async def check(self, request, context, memory, pending_state):
        return SkillMatch(
            matched=self.outcome is SkillOutcome.HANDLED,
            token="skill-a" if self.outcome is SkillOutcome.HANDLED else None,
            outcome=self.outcome,
            text="Which device?" if self.outcome is SkillOutcome.NEEDS_CLARIFICATION else None,
            pending_state={"missing": "target"} if self.outcome is SkillOutcome.NEEDS_CLARIFICATION else None,
            error_code="SKILL_FAILED" if self.outcome is SkillOutcome.FAILED else None,
        )

    async def execute(self, match, request, context, memory, pending_state):
        self.executed += 1
        return LifecycleDecision.completed("Handled.")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        (SkillOutcome.HANDLED, RequestStatus.COMPLETED),
        (SkillOutcome.NEEDS_CLARIFICATION, RequestStatus.NEEDS_CLARIFICATION),
        (SkillOutcome.FAILED, RequestStatus.FAILED),
    ],
)
async def test_only_miss_calls_llm(tmp_path, outcome, expected_status):
    llm = LlmPort()
    skill = OutcomeSkillPort(outcome)
    svc, _, _ = service(tmp_path, skill_port=skill, llm_port=llm)
    result = await svc.execute(request(kind="ha_assist", identity={
        "user_id": "user-a", "provider": "home_assistant", "confidence": 1.0
    }))
    assert result.status is expected_status
    assert llm.calls == 0


@pytest.mark.asyncio
async def test_miss_calls_llm_once(tmp_path):
    llm = LlmPort()
    skill = OutcomeSkillPort(SkillOutcome.MISS)
    svc, _, _ = service(tmp_path, skill_port=skill, llm_port=llm)
    result = await svc.execute(request(kind="ha_assist", identity={
        "user_id": "user-a", "provider": "home_assistant", "confidence": 1.0
    }))
    assert result.status is RequestStatus.COMPLETED
    assert llm.calls == 1
    assert skill.executed == 0


class UnavailableSkillsClient:
    async def check(self, request):
        raise SkillsUnavailable("offline")


@pytest.mark.asyncio
async def test_transport_unavailable_is_failed_not_miss():
    port = _RemoteSkillPort(UnavailableSkillsClient())
    match = await port.check(
        request(kind="ha_assist", identity={
            "user_id": "user-a", "provider": "home_assistant", "confidence": 1.0
        }),
        ContextResult(data={}, trace_id=new_trace_id()),
        None,
        None,
    )
    assert match.outcome is SkillOutcome.FAILED
    assert match.error_code == "SKILLS_UNAVAILABLE"
    assert match.matched is False


def test_production_app_uses_remote_skill_port_when_skills_client_is_injected(tmp_path):
    from router.app import create_app
    from router.config import RouterSettings

    class FakeSkillsClient:
        async def ready(self):
            return True

    app = create_app(
        RouterSettings(database_path=tmp_path / "router.db"),
        skills_client=FakeSkillsClient(),
    )
    assert isinstance(app.state.lifecycle.skill_port, _RemoteSkillPort)
