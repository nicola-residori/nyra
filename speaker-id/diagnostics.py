from __future__ import annotations

import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Protocol


IDENTIFIED_DETAIL_TTL = timedelta(minutes=15)
UNRESOLVED_DETAIL_TTL = timedelta(hours=24)
ORPHAN_TEMP_TTL = timedelta(hours=1)


class ConfigSnapshot(Protocol):
    threshold: float
    margin: float
    revision: int


@dataclass(frozen=True)
class DiagnosticRecord:
    diagnostic_id: str
    outcome: str
    identified_user_id: str | None
    best_score: float | None
    reason_code: str | None
    preprocessing_version: str
    model_revision: str
    config_revision: int
    threshold: float
    margin: float
    created_at: datetime
    detail_expires_at: datetime
    diagnostic_wav_path: str | None


@dataclass(frozen=True)
class DiagnosticCandidate:
    diagnostic_id: str
    user_id: str
    score: float
    rank: int


@dataclass(frozen=True)
class CleanupResult:
    expired_diagnostics: int
    deleted_wavs: int
    deleted_orphan_temp_files: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _detail_ttl(outcome: str) -> timedelta:
    if outcome == "IDENTIFIED":
        return IDENTIFIED_DETAIL_TTL
    if outcome in {"NOT_RECOGNIZED", "FAILED"}:
        return UNRESOLVED_DETAIL_TTL
    raise ValueError(f"unsupported diagnostic outcome: {outcome}")


def set_file_mtime(path: str | Path, when: datetime) -> None:
    if when.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    timestamp = when.timestamp()
    os.utime(Path(path), (timestamp, timestamp))


class DiagnosticStore:
    def __init__(self, data_root: str | Path):
        self.data_root = Path(data_root)
        self.db_path = self.data_root / "speaker_id.sqlite3"
        self.diagnostic_audio_dir = self.data_root / "diagnostics" / "audio"
        self.diagnostic_temp_dir = self.data_root / "diagnostics" / "tmp"

    def initialize(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.diagnostic_audio_dir.mkdir(parents=True, exist_ok=True)
        self.diagnostic_temp_dir.mkdir(parents=True, exist_ok=True)

        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS identification_diagnostics (
                    diagnostic_id TEXT PRIMARY KEY,
                    outcome TEXT NOT NULL,
                    identified_user_id TEXT,
                    best_score REAL,
                    reason_code TEXT,
                    preprocessing_version TEXT NOT NULL,
                    model_revision TEXT NOT NULL,
                    config_revision INTEGER NOT NULL,
                    threshold REAL NOT NULL,
                    margin REAL NOT NULL,
                    created_at TEXT,
                    detail_expires_at TEXT,
                    diagnostic_wav_path TEXT
                );

                CREATE TABLE IF NOT EXISTS diagnostic_candidates (
                    diagnostic_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    score REAL NOT NULL,
                    rank INTEGER NOT NULL,
                    PRIMARY KEY (diagnostic_id, user_id)
                );

                CREATE INDEX IF NOT EXISTS idx_diagnostic_candidates_rank
                    ON diagnostic_candidates(diagnostic_id, rank);
                """
            )
            self._ensure_column(connection, "identification_diagnostics", "created_at", "TEXT")
            self._ensure_column(connection, "identification_diagnostics", "detail_expires_at", "TEXT")
            self._ensure_column(connection, "identification_diagnostics", "diagnostic_wav_path", "TEXT")

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        table: str,
        column: str,
        sql_type: str,
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if column not in columns:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def allocate_diagnostic_wav_path(self) -> Path:
        return self.diagnostic_audio_dir / f"{uuid.uuid4().hex}.wav"

    def record(
        self,
        *,
        outcome: str,
        identified_user_id: str | None,
        best_score: float | None,
        reason_code: str | None,
        candidate_scores: Mapping[str, float],
        preprocessing_version: str,
        model_revision: str,
        config_snapshot: ConfigSnapshot,
        created_at: datetime | None = None,
        diagnostic_wav_path: str | Path | None = None,
    ) -> str:
        created = created_at or _utc_now()
        expires = created + _detail_ttl(outcome)
        wav_path = str(Path(diagnostic_wav_path)) if diagnostic_wav_path is not None else None

        diagnostic_id = uuid.uuid4().hex
        ranked = sorted(
            candidate_scores.items(),
            key=lambda item: (-item[1], item[0]),
        )

        with self._connect() as connection:
            connection.execute("BEGIN")
            try:
                connection.execute(
                    """
                    INSERT INTO identification_diagnostics (
                        diagnostic_id, outcome, identified_user_id, best_score,
                        reason_code, preprocessing_version, model_revision,
                        config_revision, threshold, margin,
                        created_at, detail_expires_at, diagnostic_wav_path
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        diagnostic_id,
                        outcome,
                        identified_user_id,
                        best_score,
                        reason_code,
                        preprocessing_version,
                        model_revision,
                        int(config_snapshot.revision),
                        float(config_snapshot.threshold),
                        float(config_snapshot.margin),
                        _serialize_datetime(created),
                        _serialize_datetime(expires),
                        wav_path,
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO diagnostic_candidates (
                        diagnostic_id, user_id, score, rank
                    ) VALUES (?, ?, ?, ?)
                    """,
                    [
                        (diagnostic_id, user_id, float(score), rank)
                        for rank, (user_id, score) in enumerate(ranked, start=1)
                    ],
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

        return diagnostic_id

    def get(self, diagnostic_id: str) -> DiagnosticRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT diagnostic_id, outcome, identified_user_id, best_score,
                       reason_code, preprocessing_version, model_revision,
                       config_revision, threshold, margin,
                       created_at, detail_expires_at, diagnostic_wav_path
                FROM identification_diagnostics
                WHERE diagnostic_id = ?
                """,
                (diagnostic_id,),
            ).fetchone()

        if row is None:
            return None

        created_at = (
            _parse_datetime(row["created_at"])
            if row["created_at"]
            else datetime.fromtimestamp(0, timezone.utc)
        )
        detail_expires_at = (
            _parse_datetime(row["detail_expires_at"])
            if row["detail_expires_at"]
            else created_at
        )

        return DiagnosticRecord(
            diagnostic_id=row["diagnostic_id"],
            outcome=row["outcome"],
            identified_user_id=row["identified_user_id"],
            best_score=row["best_score"],
            reason_code=row["reason_code"],
            preprocessing_version=row["preprocessing_version"],
            model_revision=row["model_revision"],
            config_revision=int(row["config_revision"]),
            threshold=float(row["threshold"]),
            margin=float(row["margin"]),
            created_at=created_at,
            detail_expires_at=detail_expires_at,
            diagnostic_wav_path=row["diagnostic_wav_path"],
        )

    def list_candidates(self, diagnostic_id: str) -> list[DiagnosticCandidate]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT diagnostic_id, user_id, score, rank
                FROM diagnostic_candidates
                WHERE diagnostic_id = ?
                ORDER BY rank
                """,
                (diagnostic_id,),
            ).fetchall()

        return [
            DiagnosticCandidate(
                diagnostic_id=row["diagnostic_id"],
                user_id=row["user_id"],
                score=float(row["score"]),
                rank=int(row["rank"]),
            )
            for row in rows
        ]

    def expired_detail_rows(self, now: datetime) -> list[sqlite3.Row]:
        now_value = _serialize_datetime(now)
        with self._connect() as connection:
            return connection.execute(
                """
                SELECT diagnostic_id, diagnostic_wav_path
                FROM identification_diagnostics
                WHERE detail_expires_at IS NOT NULL
                  AND detail_expires_at <= ?
                """,
                (now_value,),
            ).fetchall()

    def purge_detail(self, diagnostic_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM diagnostic_candidates WHERE diagnostic_id = ?",
                (diagnostic_id,),
            )
            connection.execute(
                """
                UPDATE identification_diagnostics
                SET detail_expires_at = NULL,
                    diagnostic_wav_path = NULL
                WHERE diagnostic_id = ?
                """,
                (diagnostic_id,),
            )


class DiagnosticHousekeeper:
    def __init__(
        self,
        store: DiagnosticStore,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ):
        self.store = store
        self.clock = clock

    def cleanup(self) -> CleanupResult:
        now = self.clock()
        expired_rows = self.store.expired_detail_rows(now)
        deleted_wavs = 0

        for row in expired_rows:
            wav_path = row["diagnostic_wav_path"]
            if wav_path:
                path = Path(wav_path)
                if path.exists():
                    path.unlink()
                    deleted_wavs += 1
            self.store.purge_detail(row["diagnostic_id"])

        deleted_orphans = self._cleanup_orphan_temp_files(now)

        return CleanupResult(
            expired_diagnostics=len(expired_rows),
            deleted_wavs=deleted_wavs,
            deleted_orphan_temp_files=deleted_orphans,
        )

    def _cleanup_orphan_temp_files(self, now: datetime) -> int:
        deleted = 0
        cutoff = now - ORPHAN_TEMP_TTL

        if not self.store.diagnostic_temp_dir.exists():
            return 0

        for path in self.store.diagnostic_temp_dir.iterdir():
            if not path.is_file():
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if modified <= cutoff:
                path.unlink()
                deleted += 1

        return deleted
