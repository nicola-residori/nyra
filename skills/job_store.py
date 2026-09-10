from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from shared.protocol.skills import JobStatus


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_storage(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _from_storage(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class JobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: JobStatus
    execute_at: datetime
    origin_request_id: str
    request_id: str | None = None
    created_trace_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    delay_seconds: float | None = None
    error: str | None = None


class JobStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._memory_connection: sqlite3.Connection | None = None
        if db_path == ":memory:":
            self._memory_connection = sqlite3.connect(":memory:", check_same_thread=False)
            self._memory_connection.row_factory = sqlite3.Row
        self._initialize()
        self.recover_interrupted()

    def _connect(self) -> sqlite3.Connection:
        if self._memory_connection is not None:
            return self._memory_connection
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _close(self, connection: sqlite3.Connection) -> None:
        if connection is not self._memory_connection:
            connection.close()

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            if self.db_path != ":memory:":
                connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    execute_at TEXT NOT NULL,
                    origin_request_id TEXT NOT NULL,
                    request_id TEXT NULL,
                    created_trace_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    started_at TEXT NULL,
                    finished_at TEXT NULL,
                    delay_seconds REAL NULL,
                    error TEXT NULL
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_due ON jobs(status, execute_at)")
            connection.commit()
        finally:
            self._close(connection)

    def is_ready(self) -> bool:
        try:
            connection = self._connect()
            try:
                connection.execute("SELECT 1").fetchone()
                return True
            finally:
                self._close(connection)
        except sqlite3.Error:
            return False

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            job_id=row["job_id"],
            status=JobStatus(row["status"]),
            execute_at=_from_storage(row["execute_at"]),
            origin_request_id=row["origin_request_id"],
            request_id=row["request_id"],
            created_trace_id=row["created_trace_id"],
            payload=json.loads(row["payload_json"]),
            created_at=_from_storage(row["created_at"]),
            started_at=_from_storage(row["started_at"]),
            finished_at=_from_storage(row["finished_at"]),
            delay_seconds=row["delay_seconds"],
            error=row["error"],
        )

    def create_scheduled(self, *, execute_at: datetime, origin_request_id: str,
                         created_trace_id: str, payload: dict[str, Any],
                         request_id: str | None = None, job_id: str | None = None,
                         now: datetime | None = None) -> JobRecord:
        created_at = now or _utc_now()
        job_id = job_id or f"job_{uuid4()}"
        connection = self._connect()
        try:
            connection.execute("""
                INSERT INTO jobs (
                    job_id, status, execute_at, origin_request_id, request_id,
                    created_trace_id, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job_id, JobStatus.SCHEDULED.value, _to_storage(execute_at),
                origin_request_id, request_id, created_trace_id,
                json.dumps(payload, separators=(",", ":"), sort_keys=True),
                _to_storage(created_at),
            ))
            connection.commit()
        finally:
            self._close(connection)
        record = self.get(job_id)
        assert record is not None
        return record

    def get(self, job_id: str) -> JobRecord | None:
        connection = self._connect()
        try:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            return self._row_to_record(row) if row is not None else None
        finally:
            self._close(connection)

    def list(self) -> list[JobRecord]:
        connection = self._connect()
        try:
            rows = connection.execute("SELECT * FROM jobs ORDER BY created_at DESC, job_id").fetchall()
            return [self._row_to_record(row) for row in rows]
        finally:
            self._close(connection)

    def list_due(self, now: datetime | None = None) -> list[JobRecord]:
        current = now or _utc_now()
        connection = self._connect()
        try:
            rows = connection.execute("""
                SELECT * FROM jobs
                WHERE status = ? AND execute_at <= ?
                ORDER BY execute_at, job_id
            """, (JobStatus.SCHEDULED.value, _to_storage(current))).fetchall()
            return [self._row_to_record(row) for row in rows]
        finally:
            self._close(connection)

    def claim_due(self, job_id: str, *, now: datetime | None = None) -> JobRecord | None:
        current = now or _utc_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                connection.rollback()
                return None
            record = self._row_to_record(row)
            if record.status is not JobStatus.SCHEDULED or record.execute_at > current:
                connection.rollback()
                return None
            delay = max(0.0, (current - record.execute_at).total_seconds())
            connection.execute("""
                UPDATE jobs
                SET status = ?, started_at = ?, delay_seconds = ?, error = NULL
                WHERE job_id = ? AND status = ?
            """, (JobStatus.RUNNING.value, _to_storage(current), delay,
                  job_id, JobStatus.SCHEDULED.value))
            connection.commit()
        finally:
            self._close(connection)
        return self.get(job_id)

    def set_terminal(self, job_id: str, status: JobStatus, *,
                     error: str | None = None, now: datetime | None = None) -> JobRecord:
        if status not in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.STOPPED, JobStatus.UNKNOWN_OUTCOME}:
            raise ValueError("terminal job status required")
        current = now or _utc_now()
        connection = self._connect()
        try:
            connection.execute("""
                UPDATE jobs SET status = ?, finished_at = ?, error = ?
                WHERE job_id = ?
            """, (status.value, _to_storage(current), error, job_id))
            connection.commit()
        finally:
            self._close(connection)
        record = self.get(job_id)
        if record is None:
            raise KeyError(job_id)
        return record

    def cancel(self, job_id: str, *, now: datetime | None = None) -> JobRecord | None:
        current = now or _utc_now()
        connection = self._connect()
        try:
            connection.execute("""
                UPDATE jobs SET status = ?, finished_at = ?
                WHERE job_id = ? AND status = ?
            """, (JobStatus.CANCELLED.value, _to_storage(current),
                  job_id, JobStatus.SCHEDULED.value))
            connection.commit()
        finally:
            self._close(connection)
        return self.get(job_id)

    def recover_interrupted(self, *, now: datetime | None = None) -> int:
        current = now or _utc_now()
        connection = self._connect()
        try:
            cursor = connection.execute("""
                UPDATE jobs
                SET status = ?, finished_at = ?, error = COALESCE(error, ?)
                WHERE status = ?
            """, (
                JobStatus.UNKNOWN_OUTCOME.value, _to_storage(current),
                "service restarted while job was RUNNING",
                JobStatus.RUNNING.value,
            ))
            connection.commit()
            return cursor.rowcount
        finally:
            self._close(connection)
