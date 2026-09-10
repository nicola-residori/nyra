from datetime import datetime, timedelta, timezone

import pytest

from shared.protocol.capabilities import ExecuteResponse
from shared.protocol.common import CommonOutcome
from shared.protocol.execution_common import NyraOperation, NyraResourceType
from shared.protocol.ids import new_request_id, new_trace_id


class Capability:
    async def execute(self, request, trusted_context):
        return ExecuteResponse(
            correlation=request.correlation,
            outcome=CommonOutcome.SUCCESS,
        )


@pytest.mark.asyncio
async def test_async_job_observability_preserves_origin_with_null_current_request(tmp_path):
    from skills.job_store import JobStore
    from skills.jobs import JobScheduler
    from skills.observability import SkillsObservability

    records = []
    store = JobStore(str(tmp_path / "jobs.sqlite3"))
    origin = new_request_id()
    scheduler = JobScheduler(
        store,
        Capability(),
        observability=SkillsObservability(records.append),
    )
    now = datetime.now(timezone.utc)
    scheduler.schedule_action(
        execute_at=now - timedelta(seconds=1),
        origin_request_id=origin,
        created_trace_id=new_trace_id(),
        operation=NyraOperation.TURN_OFF,
        resource_id="light.kitchen",
        resource_type=NyraResourceType.LIGHT,
        trusted_context={},
    )
    await scheduler.run_due(now=now)

    operations = [record.operation for record in records]
    assert "skills.job.schedule" in operations
    assert "skills.job.start" in operations
    assert "skills.job.complete" in operations
    for record in records:
        assert record.request_id is None
        assert record.origin_request_id == origin
