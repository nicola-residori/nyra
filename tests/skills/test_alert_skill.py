from datetime import datetime, timezone
import pytest
from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import (
    SkillCorrelation,
    SkillExecuteRequest,
    SkillMatch,
    SkillOutcome,
)
from skills.modules.voice_alerts import VoiceAlertsSkill
from skills.job_store import JobStore


class Scheduler:
    def __init__(self, store):
        self.store = store

    def schedule_alert(self, **kwargs):
        return self.store.create_scheduled(
            execute_at=kwargs["execute_at"],
            origin_request_id=kwargs["origin_request_id"],
            created_trace_id=kwargs["created_trace_id"],
            payload=kwargs["payload"],
        )


def request(text, identity=None, source="speaker-a"):
    return SkillExecuteRequest(
        correlation=SkillCorrelation(
            request_id=new_request_id(), trace_id=new_trace_id()
        ),
        match=SkillMatch(matched=True, skill_name="voice_alerts"),
        text=text,
        language="it",
        context={"source_id": source, "identity": identity or {}},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "resolution,name",
    [
        ("SPEAKER_IDENTIFICATION", "Nicola"),
        ("SESSION_CONTINUITY", None),
        ("TRUSTED_HA_IDENTITY", None),
        ("GUEST_FALLBACK", None),
    ],
)
async def test_name_snapshot_requires_current_biometric_identity(resolution, name):
    store = JobStore(":memory:")
    skill = VoiceAlertsSkill(
        Scheduler(store),
        timezone_name="Europe/Rome",
        now=lambda: datetime(2026, 10, 28, 12, tzinfo=timezone.utc),
    )
    response = await skill.execute(
        request(
            "chiamami tra 10 minuti",
            {
                "resolution_source": resolution,
                "display_name": "Nicola",
                "user_id": "u1",
            },
        )
    )
    assert response.outcome == SkillOutcome.HANDLED
    job = store.list()[0]
    assert job.payload["name"] == name
    assert job.payload["source_id"] == "speaker-a"
    assert job.payload["message"] == (
        "Nicola, sono passati 10 minuti." if name else "Sono passati 10 minuti."
    )
    assert job.payload["max_seconds"] == 60


@pytest.mark.asyncio
async def test_no_source_or_invalid_input_does_not_schedule():
    store = JobStore(":memory:")
    skill = VoiceAlertsSkill(Scheduler(store))
    for req in (
        request("metti un timer di zero minuti"),
        request("chiamami tra 10 minuti", source=""),
    ):
        response = await skill.execute(req)
        assert response.outcome == SkillOutcome.NEEDS_CLARIFICATION
    assert store.list() == []


@pytest.mark.asyncio
async def test_list_only_contains_origin_speaker_and_ambiguous_cancel_clarifies():
    store = JobStore(":memory:")
    skill = VoiceAlertsSkill(Scheduler(store))
    await skill.execute(request("metti un timer di 10 minuti"))
    await skill.execute(request("metti un timer di 20 minuti"))
    await skill.execute(request("metti un timer di 30 minuti", source="speaker-b"))
    listed = await skill.execute(request("elenca i timer"))
    assert len(listed.result["jobs"]) == 2
    response = await skill.execute(request("annulla il timer"))
    assert response.outcome == SkillOutcome.NEEDS_CLARIFICATION
    assert all(job.status.value == "SCHEDULED" for job in store.list())


@pytest.mark.asyncio
async def test_clarification_can_select_job_by_ordinal_without_crossing_source():
    store = JobStore(":memory:")

    class RealScheduler(Scheduler):
        async def cancel_job(self, job_id):
            return self.store.cancel(job_id)

    skill = VoiceAlertsSkill(RealScheduler(store))
    await skill.execute(request("metti un timer di 10 minuti"))
    await skill.execute(request("metti un timer di 20 minuti"))
    clarify = await skill.execute(request("annulla il timer"))
    selected = request("il primo")
    selected.pending_state = clarify.pending_state
    response = await skill.execute(selected)
    assert response.outcome == SkillOutcome.HANDLED
    assert sum(j.status.value == "CANCELLED" for j in store.list()) == 1


@pytest.mark.asyncio
async def test_incomplete_timer_accepts_duration_as_clarification():
    store = JobStore(":memory:")
    skill = VoiceAlertsSkill(Scheduler(store))
    initial = await skill.execute(request("metti un timer di"))
    followup = request("10 minuti")
    followup.pending_state = initial.pending_state
    result = await skill.execute(followup)
    assert result.outcome == SkillOutcome.HANDLED
    assert store.list()[0].payload["duration_seconds"] == 600


@pytest.mark.asyncio
async def test_spoken_list_is_localized_and_uses_ordinals_instead_of_uuids():
    store = JobStore(":memory:")
    skill = VoiceAlertsSkill(Scheduler(store))
    await skill.execute(request("svegliami tra 10 minuti"))
    result = await skill.execute(request("elenca le sveglie"))
    assert "Sveglia" in result.text
    assert "job_" not in result.text
