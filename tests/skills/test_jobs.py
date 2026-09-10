from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from shared.protocol.capabilities import ExecuteResponse
from shared.protocol.common import CommonOutcome
from shared.protocol.execution_common import NyraOperation, NyraResourceType
from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import JobStatus
from skills.app import create_app
from skills.job_store import JobStore
from skills.jobs import JobScheduler
from skills.service import SkillsService


class Capability:
    def __init__(self, outcome=CommonOutcome.SUCCESS):
        self.outcome = outcome
        self.calls = []

    async def execute(self, request, trusted_context):
        self.calls.append((request, trusted_context))
        return ExecuteResponse(
            correlation=request.correlation,
            outcome=self.outcome,
        )


@pytest.mark.asyncio
async def test_scheduler_executes_overdue_job_through_router_capability(tmp_path):
    store = JobStore(str(tmp_path / "jobs.sqlite3"))
    capability = Capability()
    scheduler = JobScheduler(store, capability)
    origin = new_request_id()
    scheduler.schedule_action(
        execute_at=datetime.now(timezone.utc) - timedelta(seconds=3),
        origin_request_id=origin,
        created_trace_id=new_trace_id(),
        operation=NyraOperation.TURN_OFF,
        resource_id="light.desk",
        resource_type=NyraResourceType.LIGHT,
        trusted_context={"authorized": True},
    )

    results = await scheduler.run_due()

    assert results[0].status is JobStatus.COMPLETED
    request, context = capability.calls[0]
    assert request.resource_id == "light.desk"
    assert request.correlation.request_id is None
    assert request.correlation.origin_request_id == origin
    assert context == {"authorized": True}


@pytest.mark.asyncio
async def test_unknown_non_idempotent_outcome_is_never_blindly_retried(tmp_path):
    store = JobStore(str(tmp_path / "jobs.sqlite3"))
    capability = Capability(CommonOutcome.UNKNOWN_OUTCOME)
    scheduler = JobScheduler(store, capability)
    job = scheduler.schedule_action(
        execute_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        origin_request_id=new_request_id(),
        created_trace_id=new_trace_id(),
        operation=NyraOperation.TRIGGER,
        resource_id="script.test",
        resource_type=NyraResourceType.SCRIPT,
        trusted_context={},
    )

    first = await scheduler.run_due()
    second = await scheduler.run_due()

    assert first[0].status is JobStatus.UNKNOWN_OUTCOME
    assert second == []
    assert len(capability.calls) == 1
    assert store.get(job.job_id).status is JobStatus.UNKNOWN_OUTCOME


def test_job_endpoints_list_get_cancel_and_safe_stop_guard(tmp_path):
    store = JobStore(str(tmp_path / "jobs.sqlite3"))
    scheduler = JobScheduler(store, Capability())
    service = SkillsService(job_store=store, scheduler=scheduler)
    job = scheduler.schedule_action(
        execute_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        origin_request_id=new_request_id(),
        created_trace_id=new_trace_id(),
        operation=NyraOperation.TURN_OFF,
        resource_id="light.desk",
        resource_type=NyraResourceType.LIGHT,
        trusted_context={},
    )

    client = TestClient(create_app(service=service))
    assert client.get("/v1/jobs").status_code == 200
    assert client.get(f"/v1/jobs/{job.job_id}").json()["job_id"] == job.job_id

    stopped = client.post(f"/v1/jobs/{job.job_id}/stop")
    assert stopped.status_code == 409

    cancelled = client.post(f"/v1/jobs/{job.job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == JobStatus.CANCELLED.value
