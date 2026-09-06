from __future__ import annotations

import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol


VALID_CAPTURE_STATUSES = {"ACCEPTED", "REJECTED", "FAILED"}


class ProcessedAudioLike(Protocol):
    wav_bytes: bytes
    preprocessing_version: str


class CaptureAlreadyCompleted(RuntimeError):
    pass


@dataclass(frozen=True)
class WakeWordSample:
    sample_id: str
    capture_id: str
    wake_word_id: str
    wake_word_text: str
    user_id: str
    source_id: str
    language: str
    created_at: datetime
    preprocessing_version: str
    wav_path: str


@dataclass(frozen=True)
class CaptureResult:
    capture_id: str
    status: str
    sample_id: str | None
    reason_code: str | None


def normalize_wake_word_text(value: str) -> tuple[str, str]:
    display = " ".join(value.strip().split())
    if not display:
        raise ValueError("wake word text cannot be empty")
    identity = display.casefold()
    return identity, display


def _serialize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class WakeWordStore:
    def __init__(self, data_root: str | Path):
        self.data_root = Path(data_root)
        self.db_path = self.data_root / "speaker_id.sqlite3"
        self.audio_root = self.data_root / "wake_words" / "audio"

    def initialize(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.audio_root.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS wake_word_captures (
                    capture_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    reason_code TEXT,
                    sample_id TEXT,
                    completed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS wake_word_samples (
                    sample_id TEXT PRIMARY KEY,
                    capture_id TEXT NOT NULL UNIQUE,
                    wake_word_id TEXT NOT NULL,
                    wake_word_text TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    language TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    preprocessing_version TEXT NOT NULL,
                    wav_path TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_wake_word_samples_identity_created
                    ON wake_word_samples(wake_word_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_wake_word_samples_created
                    ON wake_word_samples(created_at DESC);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def complete_capture(
        self,
        *,
        capture_id: str,
        status: str,
        wake_word_text: str,
        user_id: str,
        source_id: str,
        language: str,
        created_at: datetime,
        processed_audio: ProcessedAudioLike | None,
        reason_code: str | None = None,
    ) -> CaptureResult:
        if status not in VALID_CAPTURE_STATUSES:
            raise ValueError(f"unsupported capture status: {status}")

        wake_word_id, display_text = normalize_wake_word_text(wake_word_text)

        sample_id: str | None = None
        wav_path: Path | None = None

        if status == "ACCEPTED":
            if processed_audio is None:
                raise ValueError("accepted capture requires processed audio")
            sample_id = uuid.uuid4().hex
            wav_path = self.audio_root / wake_word_id.replace("/", "_") / f"{sample_id}.wav"

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT capture_id FROM wake_word_captures WHERE capture_id = ?",
                (capture_id,),
            ).fetchone()
            if existing is not None:
                raise CaptureAlreadyCompleted(capture_id)

            if wav_path is not None:
                wav_path.parent.mkdir(parents=True, exist_ok=True)
                wav_path.write_bytes(processed_audio.wav_bytes)

            connection.execute("BEGIN")
            try:
                connection.execute(
                    """
                    INSERT INTO wake_word_captures (
                        capture_id, status, reason_code, sample_id, completed_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        capture_id,
                        status,
                        reason_code,
                        sample_id,
                        _serialize_datetime(created_at),
                    ),
                )

                if status == "ACCEPTED":
                    connection.execute(
                        """
                        INSERT INTO wake_word_samples (
                            sample_id, capture_id, wake_word_id, wake_word_text,
                            user_id, source_id, language, created_at,
                            preprocessing_version, wav_path
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            sample_id,
                            capture_id,
                            wake_word_id,
                            display_text,
                            user_id,
                            source_id,
                            language,
                            _serialize_datetime(created_at),
                            processed_audio.preprocessing_version,
                            str(wav_path),
                        ),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                if wav_path is not None and wav_path.exists():
                    wav_path.unlink()
                raise

        return CaptureResult(
            capture_id=capture_id,
            status=status,
            sample_id=sample_id,
            reason_code=reason_code,
        )

    def get_sample(self, sample_id: str) -> WakeWordSample | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT sample_id, capture_id, wake_word_id, wake_word_text,
                       user_id, source_id, language, created_at,
                       preprocessing_version, wav_path
                FROM wake_word_samples
                WHERE sample_id = ?
                """,
                (sample_id,),
            ).fetchone()

        if row is None:
            return None
        return self._sample_from_row(row)

    def get_samples(self, sample_ids: Iterable[str]) -> list[WakeWordSample]:
        result: list[WakeWordSample] = []
        for sample_id in sample_ids:
            sample = self.get_sample(sample_id)
            if sample is not None:
                result.append(sample)
        return result

    def list_samples(self, wake_word_id: str | None = None) -> list[WakeWordSample]:
        with self._connect() as connection:
            if wake_word_id is None:
                rows = connection.execute(
                    """
                    SELECT sample_id, capture_id, wake_word_id, wake_word_text,
                           user_id, source_id, language, created_at,
                           preprocessing_version, wav_path
                    FROM wake_word_samples
                    ORDER BY created_at DESC, sample_id DESC
                    """
                ).fetchall()
            else:
                normalized, _ = normalize_wake_word_text(wake_word_id)
                rows = connection.execute(
                    """
                    SELECT sample_id, capture_id, wake_word_id, wake_word_text,
                           user_id, source_id, language, created_at,
                           preprocessing_version, wav_path
                    FROM wake_word_samples
                    WHERE wake_word_id = ?
                    ORDER BY created_at DESC, sample_id DESC
                    """,
                    (normalized,),
                ).fetchall()

        return [self._sample_from_row(row) for row in rows]

    def delete_sample(self, sample_id: str) -> bool:
        sample = self.get_sample(sample_id)
        if sample is None:
            return False

        with self._connect() as connection:
            connection.execute(
                "DELETE FROM wake_word_samples WHERE sample_id = ?",
                (sample_id,),
            )
            connection.execute(
                """
                UPDATE wake_word_captures
                SET sample_id = NULL
                WHERE capture_id = ?
                """,
                (sample.capture_id,),
            )

        path = Path(sample.wav_path)
        if path.exists():
            path.unlink()
        return True

    def delete_samples(self, sample_ids: Iterable[str]) -> int:
        deleted = 0
        for sample_id in list(sample_ids):
            if self.delete_sample(sample_id):
                deleted += 1
        return deleted

    def _sample_from_row(self, row: sqlite3.Row) -> WakeWordSample:
        return WakeWordSample(
            sample_id=row["sample_id"],
            capture_id=row["capture_id"],
            wake_word_id=row["wake_word_id"],
            wake_word_text=row["wake_word_text"],
            user_id=row["user_id"],
            source_id=row["source_id"],
            language=row["language"],
            created_at=_parse_datetime(row["created_at"]),
            preprocessing_version=row["preprocessing_version"],
            wav_path=row["wav_path"],
        )
