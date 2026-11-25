from datetime import datetime, timezone
import pytest
from skills.app import _default_service
from skills.config import SkillsSettings
from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillExecuteRequest,
    SkillCorrelation,
    SkillOutcome,
)


@pytest.mark.asyncio
async def test_production_registration_schedules_real_persisted_alarm(tmp_path):
    service = _default_service(
        SkillsSettings(
            job_db_path=str(tmp_path / "jobs.db"), router_url="http://router"
        )
    )
    correlation = SkillCorrelation(request_id=new_request_id(), trace_id=new_trace_id())
    check = SkillCheckRequest(
        correlation=correlation,
        text="svegliami tra 10 minuti",
        language="it",
        context={"source_id": "speaker-a"},
    )
    match = await service.check(check)
    assert match.outcome == SkillOutcome.HANDLED
    assert match.match.skill_name == "voice_alerts"
    result = await service.execute(
        SkillExecuteRequest(
            correlation=correlation,
            match=match.match,
            text=check.text,
            language="it",
            context=check.context,
        )
    )
    assert result.outcome == SkillOutcome.HANDLED
    job = service.get_job(result.result["job_id"])
    assert job.payload["alert_kind"] == "alarm"
    assert job.payload["max_seconds"] == 60
    assert job.status.value == "SCHEDULED"
    assert service.is_ready()
