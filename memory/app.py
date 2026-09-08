from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from time import monotonic

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from memory.config import MemorySettings
from memory.embeddings import SentenceTransformerEmbeddingProvider
from memory.api.operational import router as operational_router
from memory.api.semantic import router as semantic_router
from memory.observability import MemoryObservability
from memory.operational import OperationalContextService
from memory.semantic import SemanticMemoryService
from memory.storage import MemoryStore
from shared.logging.client import NyraLogger


def create_app(
    settings: MemorySettings | None = None,
    *,
    embedding_provider=None,
    event_sink=None,
) -> FastAPI:
    settings = settings or MemorySettings.load()
    provider = embedding_provider or SentenceTransformerEmbeddingProvider(
        settings.embedding_model
    )
    store = MemoryStore(settings.database_path)
    operational_context = OperationalContextService(store)
    semantic_memory = SemanticMemoryService(store, provider)
    memory_observability = MemoryObservability(event_sink)
    started = monotonic()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ready = False
        owned_logger = None
        if event_sink is None:
            owned_logger = NyraLogger(
                settings.router_url,
                "MEMORY",
                {},
                spool_path=settings.data_root / "log-spool.jsonl",
            )
            memory_observability.event_sink = owned_logger
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
            if owned_logger is not None:
                owned_logger.close()

    app = FastAPI(title="Nyra Memory", lifespan=lifespan)
    app.state.ready = False
    app.state.storage_state = "not_initialized"
    app.state.embedding_state = "not_loaded"
    app.state.embedding_provider = provider
    app.state.settings = settings
    app.state.store = store
    app.state.operational_context = operational_context
    app.state.semantic_memory = semantic_memory
    app.state.memory_observability = memory_observability

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
    app.include_router(semantic_router)

    return app


app = create_app()
