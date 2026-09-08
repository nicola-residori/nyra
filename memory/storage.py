from __future__ import annotations

import sqlite3
from pathlib import Path


class MemoryStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS operational_entries (
                    entry_id TEXT PRIMARY KEY,
                    entry_type TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    owner_user_id TEXT,
                    key TEXT NOT NULL,
                    normalized_key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    revision INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK (scope = 'USER' OR owner_user_id IS NULL),
                    CHECK (scope != 'USER' OR owner_user_id IS NOT NULL)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_operational_resolution
                ON operational_entries (
                    entry_type, normalized_key, enabled, scope, owner_user_id
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS idempotency_results (
                    idempotency_key TEXT PRIMARY KEY,
                    operation TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
