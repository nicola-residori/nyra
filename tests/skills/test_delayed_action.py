import inspect

import pytest

from shared.protocol.capabilities import (
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
from skills.job_store import JobStore
from skills.jobs import JobScheduler
from skills.modules.delayed_action import DelayedActionSkill, parse_delayed_action


class Capability:
    def __init__(self):
        self.resolve_calls = []
        self.execute_calls = []

    async def resolve(self, reference, trusted_context, *, correlation):
        self.resolve_calls.append(reference)
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
                    ),
                    score=1.0,
                )
            ],
        )

    async def execute(self, request, trusted_context):
        self.execute_calls.append(request)
        return ExecuteResponse(
            correlation=request.correlation,
            outcome=CommonOutcome.SUCCESS,
        )


def _correlation():
    request_id = new_request_id()
    return SkillCorrelation(
        request_id=request_id,
        origin_request_id=request_id,
        trace_id=new_trace_id(),
    )


def test_parser_uses_ephemeral_semantics_not_duration_threshold():
    parsed = parse_delayed_action(
        "turn on the kitchen light and turn it off after 2 hours",
        "en",
    )
    assert parsed is not None
    assert parsed.initial_operation is NyraOperation.TURN_ON
    assert parsed.followup_operation is NyraOperation.TURN_OFF
    assert parsed.delay_seconds == 7200


def test_parser_supports_italian_and_rejects_standalone_future_action():
    parsed = parse_delayed_action(
        "accendi la lampada cucina e spegnila dopo 20 secondi",
        "it",
    )
    assert parsed is not None
    assert parsed.followup_operation is NyraOperation.TURN_OFF
    assert parse_delayed_action(
        "accendi la lampada cucina domani alle 8",
        "it",
    ) is None


@pytest.mark.asyncio
async def test_immediate_action_then_persisted_reversal(tmp_path):
    capability = Capability()
    store = JobStore(str(tmp_path / "jobs.sqlite3"))
    scheduler = JobScheduler(store, capability)
    skill = DelayedActionSkill(capability, scheduler)
    corr = _correlation()
    check = SkillCheckRequest(
        correlation=corr,
        text="turn on the kitchen light and turn it off after 20 seconds",
        language="en",
        context={"authorized": True},
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
    assert [call.operation for call in capability.execute_calls] == [
        NyraOperation.TURN_ON
    ]
    jobs = store.list()
    assert len(jobs) == 1
    assert jobs[0].status.value == "SCHEDULED"
    assert jobs[0].payload["operation"] == NyraOperation.TURN_OFF.value
    assert jobs[0].request_id is None
    assert jobs[0].origin_request_id == corr.origin_request_id


def test_delayed_action_has_no_direct_home_assistant_transport():
    import skills.modules.delayed_action as module

    source = inspect.getsource(module)
    assert "/api/states" not in source
    assert "/api/services/" not in source
    assert "home_assistant_token" not in source
    assert "NYRA_HOME_ASSISTANT_TOKEN" not in source
