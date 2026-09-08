from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Callable


@dataclass(frozen=True)
class UserReference:
    provider: str
    user_id: str
    display_name: str
    updated_at: datetime


class UserDirectory:
    def __init__(
        self,
        database_path: Path | str,
        *,
        clock: Callable[[], datetime] | None = None,
    ):
        self.database_path = Path(database_path)
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS trusted_user_references (
                    provider TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (provider, user_id)
                )
                """
            )

    def upsert(self, provider: str, user_id: str, display_name: str) -> UserReference:
        provider = _required(provider, "provider")
        user_id = _required(user_id, "user_id")
        display_name = _required(display_name, "display_name")
        if len(display_name) > 255:
            raise ValueError("display_name must not exceed 255 characters")
        updated_at = self.clock()
        if updated_at.tzinfo is None:
            raise ValueError("clock must return a timezone-aware datetime")

        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO trusted_user_references (
                    provider, user_id, display_name, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(provider, user_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    updated_at = excluded.updated_at
                """,
                (provider, user_id, display_name, updated_at.isoformat()),
            )
        return UserReference(provider, user_id, display_name, updated_at)

    def get(self, provider: str, user_id: str) -> UserReference | None:
        provider = _required(provider, "provider")
        user_id = _required(user_id, "user_id")
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT provider, user_id, display_name, updated_at
                FROM trusted_user_references
                WHERE provider = ? AND user_id = ?
                """,
                (provider, user_id),
            ).fetchone()
        if row is None:
            return None
        return UserReference(
            provider=row["provider"],
            user_id=row["user_id"],
            display_name=row["display_name"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()
