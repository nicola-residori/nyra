from __future__ import annotations

import sqlite3
import uuid
import httpx
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from threading import Lock


class WakeWordCaptureStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class WakeWordCaptureSession:
    session_id: str
    user_id: str
    source_id: str
    language: str
    wake_word_text: str
    status: WakeWordCaptureStatus
    sample_id: str | None = None
    reason_code: str | None = None


class WakeWordCaptureNotFound(KeyError):
    pass


class WakeWordCaptureConflict(RuntimeError):
    pass


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return " ".join(value.strip().split())


class WakeWordCaptureSessionStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self._lock = Lock()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS wake_word_capture_sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    language TEXT NOT NULL,
                    wake_word_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sample_id TEXT,
                    reason_code TEXT
                )
            """)
            connection.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_wake_word_capture_active_source
                ON wake_word_capture_sessions(source_id)
                WHERE status = 'ACTIVE'
            """)

    def create(self, session: WakeWordCaptureSession) -> WakeWordCaptureSession:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO wake_word_capture_sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                self._values(session),
            )
        return session

    def get(self, session_id: str) -> WakeWordCaptureSession:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM wake_word_capture_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise WakeWordCaptureNotFound(session_id)
        return self._from_row(row)

    def get_active_for_source(self, source_id: str) -> WakeWordCaptureSession | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM wake_word_capture_sessions WHERE source_id = ? AND status = 'ACTIVE'",
                (source_id,),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def complete(self, session_id: str, status: WakeWordCaptureStatus,
                 sample_id: str | None, reason_code: str | None) -> WakeWordCaptureSession:
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM wake_word_capture_sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise WakeWordCaptureNotFound(session_id)
            current = self._from_row(row)
            if current.status is not WakeWordCaptureStatus.ACTIVE:
                raise WakeWordCaptureConflict("wake-word capture session is terminal")
            completed = replace(
                current, status=status, sample_id=sample_id, reason_code=reason_code
            )
            connection.execute(
                """UPDATE wake_word_capture_sessions
                   SET status=?, sample_id=?, reason_code=? WHERE session_id=?""",
                (status.value, sample_id, reason_code, session_id),
            )
            connection.commit()
        return completed

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _values(session: WakeWordCaptureSession) -> tuple:
        return (
            session.session_id, session.user_id, session.source_id, session.language,
            session.wake_word_text, session.status.value, session.sample_id,
            session.reason_code,
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> WakeWordCaptureSession:
        return WakeWordCaptureSession(
            session_id=row["session_id"], user_id=row["user_id"],
            source_id=row["source_id"], language=row["language"],
            wake_word_text=row["wake_word_text"],
            status=WakeWordCaptureStatus(row["status"]), sample_id=row["sample_id"],
            reason_code=row["reason_code"],
        )


class WakeWordCaptureService:
    def __init__(self, store: WakeWordCaptureSessionStore, event_sink=None):
        self.store = store
        self.event_sink = event_sink

    def _emit(self, event: str, session: WakeWordCaptureSession, *, result: str | None = None,
              **params) -> None:
        if self.event_sink is None:
            return
        self.event_sink.emit(
            event,
            operation="wake_word_capture",
            result=result,
            params={
                "wake_word_session_id": session.session_id,
                "user_id": session.user_id,
                "source_id": session.source_id,
                "wake_word_text": session.wake_word_text,
                **params,
            },
        )

    def start(self, user_id: str, source_id: str, language: str,
              wake_word_text: str) -> WakeWordCaptureSession:
        user_id = _required(user_id, "user_id")
        source_id = _required(source_id, "source_id")
        language = _required(language, "language")
        wake_word_text = _required(wake_word_text, "wake_word_text")
        if self.store.get_active_for_source(source_id) is not None:
            raise WakeWordCaptureConflict("ACTIVE_WAKE_WORD_CAPTURE_CONFLICT")
        session = self.store.create(WakeWordCaptureSession(
            session_id=f"wwc_{uuid.uuid4().hex}", user_id=user_id,
            source_id=source_id, language=language, wake_word_text=wake_word_text,
            status=WakeWordCaptureStatus.ACTIVE,
        ))
        self._emit(
            "wake_word.capture.started",
            session,
            result=session.status.value,
            language=session.language,
        )
        return session

    def get(self, session_id: str) -> WakeWordCaptureSession:
        return self.store.get(session_id)

    def complete(self, session_id: str, status: str, *, sample_id: str | None = None,
                 reason_code: str | None = None) -> WakeWordCaptureSession:
        try:
            terminal = WakeWordCaptureStatus(status)
        except ValueError as exc:
            raise ValueError("invalid wake-word capture status") from exc
        if terminal is WakeWordCaptureStatus.ACTIVE:
            raise ValueError("capture result must be terminal")
        if terminal is WakeWordCaptureStatus.ACCEPTED and not sample_id:
            raise ValueError("accepted capture requires sample_id")
        if terminal is not WakeWordCaptureStatus.ACCEPTED and sample_id is not None:
            raise ValueError("non-accepted capture cannot include sample_id")
        session = self.store.complete(session_id, terminal, sample_id, reason_code)
        self._emit(
            f"wake_word.capture.{terminal.value.lower()}",
            session,
            result=terminal.value,
            sample_id=sample_id,
            reason_code=reason_code,
        )
        self._emit(
            "wake_word.capture.completed",
            session,
            result=terminal.value,
            sample_id=sample_id,
            reason_code=reason_code,
        )
        return session


class SpeakerWakeWordDatasetClient:
    def __init__(self, base_url: str | None, *, timeout: float = 5.0):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout = timeout

    async def count(self, wake_word_text: str) -> int:
        if self.base_url is None:
            raise RuntimeError("Speaker-ID dataset API is unavailable")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.base_url}/v1/wake-word-samples/count",
                params={"wake_word_text": wake_word_text}, timeout=self.timeout,
            )
        response.raise_for_status()
        data = response.json()
        count = data.get("sample_count") if isinstance(data, dict) else None
        if type(count) is not int or count < 0:
            raise RuntimeError("Speaker-ID returned an invalid sample count")
        return count


def speaker_id_http_url(explicit: str | None, stream_url: str | None) -> str | None:
    if explicit:
        return explicit.rstrip("/")
    if not stream_url:
        return None
    value = stream_url.rstrip("/")
    if value.endswith("/v1/audio/stream"):
        value = value[:-len("/v1/audio/stream")]
    if value.startswith("ws://"):
        return "http://" + value[5:]
    if value.startswith("wss://"):
        return "https://" + value[6:]
    return None
