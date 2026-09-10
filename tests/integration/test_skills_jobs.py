from datetime import datetime, timedelta, timezone
import sqlite3

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
from skills.modules import register_builtin_skills
from skills.registry import SkillRegistry
from skills.service import SkillsService


class RouterCapability:
    def __init__(self):
        self.resolve_calls = []
        self.execute_calls = []

    async def resolve(self, reference, trusted_context, *, correlation):
        self.resolve_calls.append((reference, trusted_context))
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


@pytest.mark.asyncio
async def test_delayed_skill_round_trip_uses_router_capability_only(tmp_path):
    capability = RouterCapability()
    store = JobStore(str(tmp_path / "jobs.sqlite3"))
    scheduler = JobScheduler(store, capability)
    registry = SkillRegistry()
    register_builtin_skills(
        registry,
        home_assistant_capability=capability,
        job_scheduler=scheduler,
    )
    service = SkillsService(
        registry=registry,
        job_store=store,
        scheduler=scheduler,
    )

    request_id = new_request_id()
    corr = SkillCorrelation(
        request_id=request_id,
        origin_request_id=request_id,
        trace_id=new_trace_id(),
    )
    check_request = SkillCheckRequest(
        correlation=corr,
        text="turn on the kitchen light and turn it off after 20 seconds",
        language="en",
        context={"policy": "allowed"},
    )
    checked = await service.check(check_request)
    assert checked.outcome is SkillOutcome.HANDLED
    assert checked.match.skill_name == "delayed_action"

    executed = await service.execute(
        SkillExecuteRequest(
            correlation=corr,
            match=checked.match,
            text=check_request.text,
            language=check_request.language,
            context=check_request.context,
        )
    )
    assert executed.outcome is SkillOutcome.HANDLED
    assert len(capability.execute_calls) == 1
    assert capability.execute_calls[0][0].operation is NyraOperation.TURN_ON

    job = store.list()[0]
    due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    with sqlite3.connect(store.db_path) as connection:
        connection.execute(
            "UPDATE jobs SET execute_at = ? WHERE job_id = ?",
            (due_at.isoformat(), job.job_id),
        )
        connection.commit()

    completed = await scheduler.run_due()
    assert completed[0].status.value == "COMPLETED"
    assert len(capability.execute_calls) == 2
    delayed_request = capability.execute_calls[1][0]
    assert delayed_request.operation is NyraOperation.TURN_OFF
    assert delayed_request.resource_id == "light.kitchen"
    assert delayed_request.correlation.request_id is None
    assert delayed_request.correlation.origin_request_id == request_id
