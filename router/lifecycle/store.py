from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import json
import sqlite3
from uuid import UUID
from router.lifecycle.models import PersistedRequestState
from shared.protocol.requests import RequestStatus


class RequestStateStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self):
        with self._connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS request_states (
                request_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                type TEXT NOT NULL,
                language TEXT NOT NULL,
                source_json TEXT,
                identity_user_id TEXT,
                original_input TEXT NOT NULL,
                status TEXT NOT NULL,
                current_trace_id TEXT NOT NULL,
                pending_state_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                expires_at TEXT
            )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_request_states_session_id ON request_states(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_request_states_status ON request_states(status)")

    @staticmethod
    def _row(state: PersistedRequestState):
        d = state.model_dump(mode="json")
        return (
            d["request_id"], d["session_id"], d["type"], d["language"],
            json.dumps(d["source"], ensure_ascii=False) if d["source"] is not None else None,
            d["identity_user_id"], d["original_input"], d["status"], d["current_trace_id"],
            json.dumps(d["pending_state"], ensure_ascii=False) if d["pending_state"] is not None else None,
            d["created_at"], d["updated_at"], d["expires_at"],
        )

    def create(self, state: PersistedRequestState) -> None:
        with self._connection() as conn:
            conn.execute("""INSERT INTO request_states(
                request_id,session_id,type,language,source_json,identity_user_id,original_input,status,
                current_trace_id,pending_state_json,created_at,updated_at,expires_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", self._row(state))

    def update(self, state: PersistedRequestState) -> None:
        row = self._row(state)
        with self._connection() as conn:
            conn.execute("""UPDATE request_states SET
                session_id=?,type=?,language=?,source_json=?,identity_user_id=?,original_input=?,status=?,
                current_trace_id=?,pending_state_json=?,created_at=?,updated_at=?,expires_at=?
                WHERE request_id=?""", row[1:] + (row[0],))

    @staticmethod
    def _decode(row) -> PersistedRequestState | None:
        if row is None:
            return None
        d = dict(row)
        d["source"] = json.loads(d.pop("source_json")) if d["source_json"] else None
        d["pending_state"] = json.loads(d.pop("pending_state_json")) if d["pending_state_json"] else None
        return PersistedRequestState.model_validate(d)

    def get(self, request_id: str | UUID) -> PersistedRequestState | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM request_states WHERE request_id=?", (str(request_id),)).fetchone()
        return self._decode(row)

    def get_session_id_for_request(self, request_id: str | UUID) -> str | None:
        state = self.get(request_id)
        return state.session_id if state is not None else None

    def get_latest_for_session(self, session_id: str) -> PersistedRequestState | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM request_states WHERE session_id=? ORDER BY updated_at DESC, rowid DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        return self._decode(row)

    def expire_due(self, now: datetime) -> int:
        with self._connection() as conn:
            cur = conn.execute("""UPDATE request_states SET status=?, updated_at=?
                WHERE status=? AND expires_at IS NOT NULL AND expires_at<=?""",
                (RequestStatus.EXPIRED.value, now.isoformat(), RequestStatus.NEEDS_CLARIFICATION.value, now.isoformat()))
            return cur.rowcount
