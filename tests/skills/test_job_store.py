from datetime import datetime, timedelta, timezone
import sqlite3

from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import JobStatus
from skills.job_store import JobStore


NOW = datetime(2026, 9, 10, 8, 0, tzinfo=timezone.utc)


def _create(store, *, execute_at=None):
    return store.create_scheduled(
        execute_at=execute_at or NOW + timedelta(seconds=30),
        origin_request_id=new_request_id(),
        request_id=None,
        created_trace_id=new_trace_id(),
        payload={"kind": "test", "value": 1},
        now=NOW,
    )


def test_sqlite_store_uses_wal_and_scheduled_survives_reopen(tmp_path):
    db = tmp_path / "jobs.sqlite3"
    store = JobStore(str(db))
    job = _create(store)

    with sqlite3.connect(db) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    reopened = JobStore(str(db))
    persisted = reopened.get(job.job_id)
    assert persisted is not None
    assert persisted.status is JobStatus.SCHEDULED
    assert persisted.payload == {"kind": "test", "value": 1}


def test_running_becomes_unknown_outcome_after_simulated_restart(tmp_path):
    db = tmp_path / "jobs.sqlite3"
    store = JobStore(str(db))
    job = _create(store, execute_at=NOW - timedelta(seconds=5))
    running = store.claim_due(job.job_id, now=NOW)
    assert running is not None
    assert running.status is JobStatus.RUNNING

    reopened = JobStore(str(db))
    recovered = reopened.get(job.job_id)
    assert recovered is not None
    assert recovered.status is JobStatus.UNKNOWN_OUTCOME
    assert recovered.error is not None


def test_cancelled_never_starts_and_overdue_job_is_immediately_due(tmp_path):
    store = JobStore(str(tmp_path / "jobs.sqlite3"))
    cancelled = _create(store, execute_at=NOW - timedelta(seconds=1))
    overdue = _create(store, execute_at=NOW - timedelta(seconds=12))
    store.cancel(cancelled.job_id, now=NOW)

    due_ids = [item.job_id for item in store.list_due(NOW)]
    assert cancelled.job_id not in due_ids
    assert overdue.job_id in due_ids

    claimed = store.claim_due(overdue.job_id, now=NOW)
    assert claimed is not None
    assert claimed.status is JobStatus.RUNNING
    assert claimed.delay_seconds == 12.0


def test_job_preserves_origin_without_fabricating_current_request(tmp_path):
    store = JobStore(str(tmp_path / "jobs.sqlite3"))
    origin = new_request_id()
    job = store.create_scheduled(
        execute_at=NOW + timedelta(seconds=10),
        origin_request_id=origin,
        request_id=None,
        created_trace_id=new_trace_id(),
        payload={"kind": "test"},
        now=NOW,
    )
    assert job.origin_request_id == origin
    assert job.request_id is None
