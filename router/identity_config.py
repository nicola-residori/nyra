from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from threading import RLock


DEFAULT_IDENTIFICATION_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class IdentityTimeoutSnapshot:
    identification_timeout_seconds: float
    revision: int


class IdentityRuntimeConfigStore:
    def __init__(self, database_path: str | Path, default_timeout_seconds: float = DEFAULT_IDENTIFICATION_TIMEOUT_SECONDS):
        self.database_path = Path(database_path)
        self.default_timeout_seconds = float(default_timeout_seconds)
        self._lock = RLock()

    def _connect(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS router_runtime_config (
                    config_key TEXT PRIMARY KEY,
                    config_value REAL NOT NULL,
                    revision INTEGER NOT NULL
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO router_runtime_config(config_key, config_value, revision)
                VALUES ('identification_timeout_seconds', ?, 1)
            """, (self.default_timeout_seconds,))

    def snapshot(self) -> IdentityTimeoutSnapshot:
        self.initialize()
        with self._lock, self._connect() as conn:
            row = conn.execute("""
                SELECT config_value, revision
                FROM router_runtime_config
                WHERE config_key='identification_timeout_seconds'
            """).fetchone()
        return IdentityTimeoutSnapshot(float(row["config_value"]), int(row["revision"]))

    def update_identification_timeout(self, seconds: float) -> IdentityTimeoutSnapshot:
        seconds = float(seconds)
        if seconds <= 0:
            raise ValueError("identification timeout must be > 0 seconds")
        with self._lock:
            self.initialize()
            with self._connect() as conn:
                conn.execute("""
                    UPDATE router_runtime_config
                    SET config_value=?, revision=revision+1
                    WHERE config_key='identification_timeout_seconds'
                """, (seconds,))
        return self.snapshot()
