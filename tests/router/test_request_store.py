from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from router.lifecycle.models import PersistedRequestState
from router.lifecycle.store import RequestStateStore
from shared.protocol.requests import ExecutionType, RequestStatus
from router.observability.ids import generate_request_id, generate_session_id, generate_trace_id


def make_state(now):
    return PersistedRequestState(
        request_id=generate_request_id(), session_id=generate_session_id(), type=ExecutionType.HA_SPEAKER,
        language="it", source={"id":"speaker-a","area":"living-room"}, identity_user_id=None,
        original_input="turn on the light", status=RequestStatus.NEEDS_CLARIFICATION,
        current_trace_id=generate_trace_id(), pending_state={"missing":"entity"}, created_at=now, updated_at=now,
        expires_at=now + timedelta(seconds=120),
    )


def test_request_state_roundtrip_and_update(tmp_path: Path):
    now = datetime(2026, 8, 30, 20, 0, tzinfo=timezone.utc)
    store = RequestStateStore(tmp_path / "router.db")
    store.initialize()
    state = make_state(now)
    store.create(state)
    loaded = store.get(state.request_id)
    assert loaded.pending_state == {"missing":"entity"}
    assert loaded.source.id == "speaker-a"
    loaded.identity_user_id = "user-a"
    loaded.status = RequestStatus.COMPLETED
    loaded.pending_state = None
    loaded.updated_at = now + timedelta(seconds=10)
    store.update(loaded)
    assert store.get(state.request_id).identity_user_id == "user-a"
    assert store.get(state.request_id).status is RequestStatus.COMPLETED


def test_expire_due_marks_only_pending_requests(tmp_path: Path):
    now = datetime(2026, 8, 30, 20, 2, 1, tzinfo=timezone.utc)
    store = RequestStateStore(tmp_path / "router.db")
    store.initialize()
    state = make_state(now - timedelta(seconds=121))
    store.create(state)
    assert store.expire_due(now) == 1
    assert store.get(state.request_id).status is RequestStatus.EXPIRED


def test_store_returns_latest_request_for_session(tmp_path: Path):
    now = datetime(2026, 8, 30, 20, 0, tzinfo=timezone.utc)
    store = RequestStateStore(tmp_path / "router.db")
    store.initialize()
    first = make_state(now)
    first.status = RequestStatus.COMPLETED
    first.identity_user_id = "user-a"
    store.create(first)
    second = make_state(now + timedelta(seconds=5))
    second.session_id = first.session_id
    second.identity_user_id = "user-b"
    store.create(second)
    assert store.get_latest_for_session(first.session_id).request_id == second.request_id


def test_store_explicitly_closes_connection_after_operation(tmp_path: Path):
    store = RequestStateStore(tmp_path / "router.db")
    raw = sqlite3.connect(tmp_path / "tracked.db")

    class TrackingConnection:
        def __init__(self, connection):
            self.connection = connection
            self.closed = False

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, exc_type, exc, tb):
            return self.connection.__exit__(exc_type, exc, tb)

        def close(self):
            self.closed = True
            self.connection.close()

    tracked = TrackingConnection(raw)
    store._connect = lambda: tracked

    store.initialize()

    assert tracked.closed is True
