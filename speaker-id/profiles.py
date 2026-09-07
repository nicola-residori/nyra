from __future__ import annotations

import json
import sqlite3
import threading
import uuid
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class SpeakerProfile:
    user_id: str
    centroid: list[float]
    sample_count: int


@dataclass(frozen=True)
class EnrollmentSample:
    sample_id: str
    user_id: str
    source_id: str | None
    wav_path: str
    embedding: list[float]
    quality: dict
    preprocessing_version: str
    created_at: datetime | None = None
    duration_seconds: float | None = None


class ProfileStore:
    def __init__(self, data_root: str | Path):
        self.data_root = Path(data_root)
        self.db_path = self.data_root / "speaker_id.sqlite3"
        self.samples_root = self.data_root / "samples"
        self._lock = threading.RLock()
        self.rebuild_count = 0

    def initialize(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.samples_root.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS speaker_profiles (
                    user_id TEXT PRIMARY KEY,
                    centroid_json TEXT NOT NULL,
                    sample_count INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS enrollment_samples (
                    sample_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    source_id TEXT,
                    wav_path TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    quality_json TEXT NOT NULL,
                    preprocessing_version TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_enrollment_samples_user
                    ON enrollment_samples(user_id);
                """
            )
            self._ensure_column(connection, "enrollment_samples", "created_at", "TEXT")
            self._ensure_column(connection, "enrollment_samples", "duration_seconds", "REAL")
            rows = connection.execute(
                "SELECT sample_id, wav_path FROM enrollment_samples WHERE created_at IS NULL OR duration_seconds IS NULL"
            ).fetchall()
            for row in rows:
                path = Path(row["wav_path"])
                created_at = (datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
                              if path.exists() else datetime.now(timezone.utc).isoformat())
                duration = None
                if path.exists():
                    try:
                        with wave.open(str(path), "rb") as audio:
                            duration = audio.getnframes() / audio.getframerate()
                    except (wave.Error, OSError, ZeroDivisionError):
                        pass
                connection.execute(
                    """UPDATE enrollment_samples
                       SET created_at=COALESCE(created_at, ?),
                           duration_seconds=COALESCE(duration_seconds, ?)
                       WHERE sample_id=?""",
                    (created_at, duration, row["sample_id"]),
                )

    @staticmethod
    def _ensure_column(connection, table: str, column: str, sql_type: str) -> None:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def add_sample(
        self,
        *,
        user_id: str,
        source_id: str | None,
        wav_bytes: bytes,
        embedding: list[float],
        quality: dict,
        preprocessing_version: str = "unknown",
        duration_seconds: float | None = None,
        created_at: datetime | None = None,
    ) -> EnrollmentSample:
        if not user_id:
            raise ValueError("user_id is required")
        if not embedding:
            raise ValueError("embedding is required")

        sample_id = uuid.uuid4().hex
        created_at = created_at or datetime.now(timezone.utc)
        if created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        user_dir = self.samples_root / _safe_path_component(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)
        wav_path = user_dir / f"{sample_id}.wav"

        with self._lock:
            wav_path.write_bytes(wav_bytes)
            connection = self._connect()
            try:
                connection.execute("BEGIN")
                self._insert_sample_metadata(
                    connection,
                    sample_id=sample_id,
                    user_id=user_id,
                    source_id=source_id,
                    wav_path=str(wav_path),
                    embedding=embedding,
                    quality=quality,
                    preprocessing_version=preprocessing_version,
                    created_at=created_at,
                    duration_seconds=duration_seconds,
                )
                self._rebuild_profile(connection, user_id)
                connection.commit()
            except Exception:
                connection.rollback()
                wav_path.unlink(missing_ok=True)
                raise
            finally:
                connection.close()

        return EnrollmentSample(
            sample_id=sample_id,
            user_id=user_id,
            source_id=source_id,
            wav_path=str(wav_path),
            embedding=list(embedding),
            quality=dict(quality),
            preprocessing_version=preprocessing_version,
            created_at=created_at.astimezone(timezone.utc),
            duration_seconds=duration_seconds,
        )

    def _insert_sample_metadata(
        self,
        connection: sqlite3.Connection,
        *,
        sample_id: str,
        user_id: str,
        source_id: str | None,
        wav_path: str,
        embedding: list[float],
        quality: dict,
        preprocessing_version: str,
        created_at: datetime,
        duration_seconds: float | None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO enrollment_samples (
                sample_id, user_id, source_id, wav_path,
                embedding_json, quality_json, preprocessing_version,
                created_at, duration_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                user_id,
                source_id,
                wav_path,
                json.dumps(list(embedding)),
                json.dumps(quality),
                preprocessing_version,
                created_at.astimezone(timezone.utc).isoformat(),
                duration_seconds,
            ),
        )

    def get_profile(self, user_id: str) -> SpeakerProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT user_id, centroid_json, sample_count FROM speaker_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return SpeakerProfile(
            user_id=row["user_id"],
            centroid=list(json.loads(row["centroid_json"])),
            sample_count=int(row["sample_count"]),
        )

    def list_samples(self, user_id: str) -> list[EnrollmentSample]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT sample_id, user_id, source_id, wav_path,
                       embedding_json, quality_json, preprocessing_version,
                       created_at, duration_seconds
                FROM enrollment_samples
                WHERE user_id = ?
                ORDER BY created_at DESC, rowid DESC
                """,
                (user_id,),
            ).fetchall()
        return [_row_to_sample(row) for row in rows]

    def list_profiles(self) -> list[SpeakerProfile]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT user_id, centroid_json, sample_count FROM speaker_profiles ORDER BY user_id"
            ).fetchall()
        return [SpeakerProfile(
            user_id=row["user_id"], centroid=list(json.loads(row["centroid_json"])),
            sample_count=int(row["sample_count"]),
        ) for row in rows]

    def get_sample(self, user_id: str, sample_id: str) -> EnrollmentSample | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT sample_id, user_id, source_id, wav_path, embedding_json,
                          quality_json, preprocessing_version, created_at, duration_seconds
                   FROM enrollment_samples WHERE user_id = ? AND sample_id = ?""",
                (user_id, sample_id),
            ).fetchone()
        return None if row is None else _row_to_sample(row)

    def delete_profile(self, user_id: str) -> int:
        return self.delete_samples(
            user_id, [sample.sample_id for sample in self.list_samples(user_id)]
        )

    def delete_samples(self, user_id: str, sample_ids: list[str]) -> int:
        unique_ids = list(dict.fromkeys(sample_ids))
        if not unique_ids:
            return 0

        placeholders = ",".join("?" for _ in unique_ids)
        with self._lock:
            connection = self._connect()
            try:
                rows = connection.execute(
                    f"""
                    SELECT sample_id, wav_path
                    FROM enrollment_samples
                    WHERE user_id = ? AND sample_id IN ({placeholders})
                    """,
                    (user_id, *unique_ids),
                ).fetchall()
                if not rows:
                    return 0

                connection.execute("BEGIN")
                connection.execute(
                    f"""
                    DELETE FROM enrollment_samples
                    WHERE user_id = ? AND sample_id IN ({placeholders})
                    """,
                    (user_id, *unique_ids),
                )
                self._rebuild_profile(connection, user_id)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()

        for row in rows:
            Path(row["wav_path"]).unlink(missing_ok=True)
        return len(rows)

    def _rebuild_profile(self, connection: sqlite3.Connection, user_id: str) -> None:
        rows = connection.execute(
            "SELECT embedding_json FROM enrollment_samples WHERE user_id = ? ORDER BY rowid",
            (user_id,),
        ).fetchall()

        self.rebuild_count += 1

        if not rows:
            connection.execute(
                "DELETE FROM speaker_profiles WHERE user_id = ?",
                (user_id,),
            )
            return

        embeddings = [list(json.loads(row["embedding_json"])) for row in rows]
        dimensions = {len(embedding) for embedding in embeddings}
        if len(dimensions) != 1 or 0 in dimensions:
            raise ValueError("sample embeddings must have one common non-zero dimension")

        count = len(embeddings)
        centroid = [
            sum(embedding[index] for embedding in embeddings) / count
            for index in range(len(embeddings[0]))
        ]

        connection.execute(
            """
            INSERT INTO speaker_profiles (user_id, centroid_json, sample_count)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                centroid_json = excluded.centroid_json,
                sample_count = excluded.sample_count
            """,
            (user_id, json.dumps(centroid), count),
        )


def _row_to_sample(row: sqlite3.Row) -> EnrollmentSample:
    return EnrollmentSample(
        sample_id=row["sample_id"],
        user_id=row["user_id"],
        source_id=row["source_id"],
        wav_path=row["wav_path"],
        embedding=list(json.loads(row["embedding_json"])),
        quality=dict(json.loads(row["quality_json"])),
        preprocessing_version=row["preprocessing_version"],
        created_at=(datetime.fromisoformat(row["created_at"]).astimezone(timezone.utc)
                    if row["created_at"] else None),
        duration_seconds=(float(row["duration_seconds"])
                          if row["duration_seconds"] is not None else None),
    )


def _safe_path_component(value: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, value).hex
