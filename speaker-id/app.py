from __future__ import annotations

import os
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Lock
from time import monotonic

from fastapi import FastAPI, WebSocket
from shared.audio_streaming import AudioStreamRegistry
from shared.audio_websocket import serve_audio
import importlib.util
import sys
from pydantic import BaseModel, Field


DEFAULT_DATA_ROOT = Path("/var/lib/nyra-speaker-id")
DEFAULT_THRESHOLD = 0.40
DEFAULT_MARGIN = 0.07
CONFIG_VERSION = 1


@dataclass(frozen=True)
class IdentificationConfigSnapshot:
    threshold: float
    margin: float
    revision: int


class IdentificationConfigUpdate(BaseModel):
    threshold: float = Field(ge=-1.0, le=1.0)
    margin: float = Field(ge=0.0, le=2.0)


class SQLiteConfigStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path
        self._lock = Lock()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_config (
                    key TEXT PRIMARY KEY,
                    threshold REAL NOT NULL,
                    margin REAL NOT NULL,
                    revision INTEGER NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO runtime_config
                    (key, threshold, margin, revision)
                VALUES ('identification', ?, ?, 1)
                """,
                (DEFAULT_THRESHOLD, DEFAULT_MARGIN),
            )

    def identification_snapshot(self) -> IdentificationConfigSnapshot:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT threshold, margin, revision
                FROM runtime_config
                WHERE key = 'identification'
                """
            ).fetchone()
        if row is None:
            raise RuntimeError("identification config is not initialized")
        return IdentificationConfigSnapshot(
            threshold=float(row[0]),
            margin=float(row[1]),
            revision=int(row[2]),
        )

    def update_identification(
        self, threshold: float, margin: float
    ) -> IdentificationConfigSnapshot:
        with self._lock:
            with self._connect() as connection:
                current = connection.execute(
                    """
                    SELECT revision
                    FROM runtime_config
                    WHERE key = 'identification'
                    """
                ).fetchone()
                if current is None:
                    raise RuntimeError("identification config is not initialized")
                revision = int(current[0]) + 1
                connection.execute(
                    """
                    UPDATE runtime_config
                    SET threshold = ?, margin = ?, revision = ?
                    WHERE key = 'identification'
                    """,
                    (threshold, margin, revision),
                )
        return IdentificationConfigSnapshot(threshold, margin, revision)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database_path)


def create_app(data_root: str | Path | None = None) -> FastAPI:
    root = Path(
        data_root
        if data_root is not None
        else os.getenv("NYRA_SPEAKER_ID_DATA_ROOT", DEFAULT_DATA_ROOT)
    )
    store = SQLiteConfigStore(root / "speaker-id.sqlite3")
    started = monotonic()
    module_name = "nyra_speaker_audio_streaming"
    module_spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name("audio_streaming.py"))
    streaming = importlib.util.module_from_spec(module_spec)
    sys.modules[module_name] = streaming
    module_spec.loader.exec_module(streaming)
    audio_sink = streaming.SpeakerAudioSink(store, root)
    audio_streams = AudioStreamRegistry(audio_sink, float(os.getenv("NYRA_AUDIO_STREAM_TIMEOUT_SECONDS", "30")))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ready = False
        root.mkdir(parents=True, exist_ok=True)
        (root / "audio").mkdir(exist_ok=True)
        store.initialize()
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            await app.state.audio_streams.close()

    app = FastAPI(title="Nyra Speaker ID", lifespan=lifespan)
    app.state.audio_streams = audio_streams
    app.state.audio_sink = audio_sink
    app.state.data_root = root
    app.state.config_store = store
    app.state.ready = False
    app.state.model_state = "not_loaded"

    @app.websocket("/v1/audio/stream")
    async def audio_stream(websocket: WebSocket):
        await serve_audio(websocket, app.state.audio_streams)

    @app.get("/health")
    def health():
        return {
            "service": "nyra-speaker-id",
            "status": "healthy",
            "uptime": round(monotonic() - started, 3),
        }

    @app.get("/ready")
    def ready():
        return {
            "ready": bool(app.state.ready),
            "storage": "initialized" if app.state.ready else "not_initialized",
            "model": app.state.model_state,
        }

    @app.get("/v1/config")
    def get_config():
        snapshot = store.identification_snapshot()
        return {
            "version": CONFIG_VERSION,
            "identification": asdict(snapshot),
        }

    @app.put("/v1/config/identification")
    def put_identification_config(update: IdentificationConfigUpdate):
        return asdict(
            store.update_identification(
                threshold=update.threshold,
                margin=update.margin,
            )
        )

    return app


app = create_app()
