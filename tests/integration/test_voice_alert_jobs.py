from datetime import datetime, timedelta, timezone
import pytest
from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import JobStatus
from shared.protocol.alerts import AlertResponse, AlertState
from skills.job_store import JobStore
from skills.jobs import JobScheduler

NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


class Audio:
    def __init__(self):
        self.states = {}
        self.starts = []
        self.offline = set()

    async def alert(self, request):
        if request.source_id in self.offline:
            return AlertResponse(state=AlertState.OFFLINE)
        if request.action == "START":
            if request.job_id not in self.states:
                self.starts.append(request.job_id)
                self.states[request.job_id] = AlertState.ACCEPTED
        if request.action == "STOP":
            self.states[request.job_id] = AlertState.STOPPED
        return AlertResponse(
            state=self.states.get(request.job_id, AlertState.NOT_FOUND)
        )


def schedule(scheduler, source="a", now=NOW):
    return scheduler.schedule_alert(
        execute_at=now,
        origin_request_id=new_request_id(),
        created_trace_id=new_trace_id(),
        payload={
            "kind": "voice_alert",
            "alert_kind": "timer",
            "source_id": source,
            "language": "it",
            "max_seconds": 60,
            "message": None,
        },
    )


@pytest.mark.asyncio
async def test_acceptance_does_not_complete_and_restart_reconciles_without_duplicate(
    tmp_path,
):
    path = str(tmp_path / "jobs.db")
    audio = Audio()
    scheduler = JobScheduler(JobStore(path), audio)
    job = schedule(scheduler)
    await scheduler.run_due(now=NOW)
    assert scheduler.store.get(job.job_id).status == JobStatus.RUNNING
    restarted = JobScheduler(JobStore(path), audio)
    await restarted.run_due(now=NOW + timedelta(seconds=2))
    assert audio.starts == [job.job_id]
    audio.states[job.job_id] = AlertState.COMPLETED
    await restarted.run_due(now=NOW + timedelta(seconds=5))
    assert restarted.store.get(job.job_id).status == JobStatus.COMPLETED


@pytest.mark.asyncio
async def test_offline_source_does_not_block_other_source_and_expires():
    audio = Audio()
    audio.offline.add("a")
    scheduler = JobScheduler(JobStore(":memory:"), audio)
    first = schedule(scheduler)
    second = schedule(scheduler, "b")
    await scheduler.run_due(now=NOW)
    assert audio.starts == [second.job_id]
    await scheduler.run_due(now=NOW + timedelta(seconds=61))
    assert scheduler.store.get(first.job_id).status == JobStatus.FAILED
    assert scheduler.store.get(first.job_id).error == "SPEAKER_OFFLINE_EXPIRED"


@pytest.mark.asyncio
async def test_same_source_fifo_stop_and_cancel_do_not_affect_others():
    audio = Audio()
    scheduler = JobScheduler(JobStore(":memory:"), audio)
    first = schedule(scheduler, now=NOW - timedelta(seconds=1))
    second = schedule(scheduler)
    await scheduler.run_due(now=NOW)
    assert audio.starts == [first.job_id]
    assert scheduler.store.get(second.job_id).status == JobStatus.SCHEDULED
    stopped = await scheduler.stop_job(first.job_id)
    assert stopped.status == JobStatus.STOPPED
    await scheduler.cancel_job(second.job_id)
    await scheduler.run_due(now=NOW)
    assert audio.starts == [first.job_id]


@pytest.mark.asyncio
async def test_running_job_missing_after_ha_restart_is_unknown_not_replayed():
    audio = Audio()
    scheduler = JobScheduler(JobStore(":memory:"), audio)
    job = schedule(scheduler)
    await scheduler.run_due(now=NOW)
    audio.states.clear()
    await scheduler.run_due(now=NOW + timedelta(seconds=1))
    assert audio.starts == [job.job_id]
    assert scheduler.store.get(job.job_id).status == JobStatus.UNKNOWN_OUTCOME


@pytest.mark.asyncio
async def test_transport_timeout_is_reconciled_by_id_before_any_retry():
    class TimeoutAfterAccept(Audio):
        async def alert(self, req):
            result = await super().alert(req)
            if req.action == "START":
                raise TimeoutError()
            return result

    audio = TimeoutAfterAccept()
    scheduler = JobScheduler(JobStore(":memory:"), audio)
    job = schedule(scheduler)
    await scheduler.run_due(now=NOW)
    await scheduler.run_due(now=NOW + timedelta(seconds=1))
    assert audio.starts == [job.job_id]
    assert scheduler.store.get(job.job_id).status == JobStatus.RUNNING


@pytest.mark.asyncio
async def test_future_schedule_survives_reopen_without_premature_audio(tmp_path):
    path = str(tmp_path / "jobs.db")
    audio = Audio()
    scheduler = JobScheduler(JobStore(path), audio)
    job = schedule(scheduler, now=NOW + timedelta(days=1))
    restarted = JobScheduler(JobStore(path), audio)
    await restarted.run_due(now=NOW)
    assert audio.starts == []
    assert restarted.store.get(job.job_id).status == JobStatus.SCHEDULED
    await restarted.run_due(now=NOW + timedelta(days=1))
    assert audio.starts == [job.job_id]


@pytest.mark.asyncio
async def test_concurrent_polls_claim_each_alert_once():
    import asyncio

    audio = Audio()
    scheduler = JobScheduler(JobStore(":memory:"), audio)
    job = schedule(scheduler)
    await asyncio.gather(scheduler.run_due(now=NOW), scheduler.run_due(now=NOW))
    assert audio.starts == [job.job_id]


@pytest.mark.asyncio
async def test_running_offline_status_does_not_delay_new_other_source():
    import asyncio

    gate = asyncio.Event()

    class SlowAudio(Audio):
        slow = False

        async def alert(self, request):
            if self.slow and request.source_id == "a":
                await gate.wait()
            return await super().alert(request)

    audio = SlowAudio()
    scheduler = JobScheduler(JobStore(":memory:"), audio)
    schedule(scheduler)
    await scheduler.run_due(now=NOW)
    audio.slow = True
    second = schedule(scheduler, "b")
    task = asyncio.create_task(scheduler.run_due(now=NOW))
    for _ in range(10):
        await asyncio.sleep(0)
    assert second.job_id in audio.starts
    gate.set()
    await task
