from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol


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


@dataclass(frozen=True)
class DiagnosticCandidate:
    diagnostic_id: str
    user_id: str
    score: float
    rank: int


class DiagnosticStore:
    def __init__(self, data_root: str | Path):
        self.data_root = Path(data_root)
        self.db_path = self.data_root / "speaker_id.sqlite3"

    def initialize(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
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
                    margin REAL NOT NULL
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

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

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
    ) -> str:
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
                        config_revision, threshold, margin
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                       config_revision, threshold, margin
                FROM identification_diagnostics
                WHERE diagnostic_id = ?
                """,
                (diagnostic_id,),
            ).fetchone()

        if row is None:
            return None

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
