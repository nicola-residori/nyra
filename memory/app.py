from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from time import monotonic

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from memory.config import MemorySettings


class _UnavailableEmbeddingProvider:
    provider_name = "sentence-transformers"

    def __init__(self, model_name: str):
        self.model_name = model_name

    def prepare(self) -> None:
        raise RuntimeError("production embedding provider is not installed")


def _initialize_database(settings: MemorySettings) -> None:
    settings.data_root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.database_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            )
            """
        )


def create_app(
    settings: MemorySettings | None = None,
    *,
    embedding_provider=None,
) -> FastAPI:
    settings = settings or MemorySettings.load()
    provider = embedding_provider or _UnavailableEmbeddingProvider(
        settings.embedding_model
    )
    started = monotonic()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ready = False
        try:
            _initialize_database(settings)
        except Exception:
            app.state.storage_state = "unavailable"
        else:
            app.state.storage_state = "initialized"

        try:
            await asyncio.to_thread(provider.prepare)
        except Exception:
            app.state.embedding_state = "unavailable"
        else:
            app.state.embedding_state = "loaded"

        app.state.ready = (
            app.state.storage_state == "initialized"
            and app.state.embedding_state == "loaded"
        )
        try:
            yield
        finally:
            app.state.ready = False

    app = FastAPI(title="Nyra Memory", lifespan=lifespan)
    app.state.ready = False
    app.state.storage_state = "not_initialized"
    app.state.embedding_state = "not_loaded"
    app.state.embedding_provider = provider
    app.state.settings = settings

    @app.get("/health")
    def health():
        return {
            "service": "nyra-memory",
            "status": "healthy",
            "uptime": round(monotonic() - started, 3),
        }

    @app.get("/ready")
    def ready():
        payload = {
            "ready": bool(app.state.ready),
            "storage": app.state.storage_state,
            "embedding": app.state.embedding_state,
            "embedding_model": provider.model_name,
        }
        if app.state.ready:
            return payload
        return JSONResponse(payload, status_code=503)

    return app


app = create_app()

