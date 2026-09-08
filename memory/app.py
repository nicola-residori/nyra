from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from time import monotonic

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from memory.config import MemorySettings
from memory.embeddings import SentenceTransformerEmbeddingProvider
from memory.api.operational import router as operational_router
from memory.operational import OperationalContextService
from memory.storage import MemoryStore


def create_app(
    settings: MemorySettings | None = None,
    *,
    embedding_provider=None,
) -> FastAPI:
    settings = settings or MemorySettings.load()
    provider = embedding_provider or SentenceTransformerEmbeddingProvider(
        settings.embedding_model
    )
    store = MemoryStore(settings.database_path)
    operational_context = OperationalContextService(store)
    started = monotonic()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ready = False
        try:
            store.initialize()
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
    app.state.store = store
    app.state.operational_context = operational_context

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

    app.include_router(operational_router)

    return app


app = create_app()
