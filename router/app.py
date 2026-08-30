from contextlib import asynccontextmanager
from time import monotonic
from fastapi import FastAPI
from router.config import RouterSettings
from router.storage.sqlite import SQLiteObservabilityStore
from router.observability.service import ObservabilityService
from router.api.health import router as health_router
from router.api.logs import router as logs_router
from router.api.observability import router as obs_router

def create_app(settings: RouterSettings|None=None):
    settings=settings or RouterSettings.load(); started=monotonic(); store=SQLiteObservabilityStore(settings.database_path)
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.initialize(); yield
    app=FastAPI(title="Nyra Router", lifespan=lifespan)
    app.state.settings=settings; app.state.store=store; app.state.observability=ObservabilityService(store); app.state.uptime=lambda: round(monotonic()-started,3)
    app.include_router(health_router); app.include_router(logs_router); app.include_router(obs_router)
    return app
app=create_app()
