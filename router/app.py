from contextlib import asynccontextmanager
from time import monotonic
from fastapi import FastAPI
from router.config import RouterSettings
from router.audio_streaming import AudioStreamRegistry, SpeakerAudioRelay
from router.storage.sqlite import SQLiteObservabilityStore
from router.observability.service import ObservabilityService
from router.lifecycle.events import InteractionEventBroker
from router.lifecycle.service import RequestLifecycleService, ContextResult, SkillMatch, LifecycleDecision
from router.lifecycle.store import RequestStateStore
from router.identity_config import IdentityRuntimeConfigStore
from shared.protocol.requests import RequestStatus
from router.api.health import router as health_router
from router.api.logs import router as logs_router
from router.api.observability import router as obs_router
from router.api.requests import router as requests_router
from router.api.audio import router as audio_router
from router.api.events import router as events_router
from router.api.identity_config import router as identity_config_router


class _IdentityPort:
    async def identify(self, request, trace_id):
        return None


class _ContextPort:
    async def resolve(self, request, identity_user_id):
        return ContextResult(data={}, semantic_memory_required=False)


class _MemoryPort:
    async def search(self, request, identity_user_id, context):
        return {}


class _SkillPort:
    async def check(self, request, context, memory, pending_state):
        return SkillMatch(matched=False)
    async def execute(self, match, request, context, memory, pending_state):
        return LifecycleDecision(status=RequestStatus.FAILED)


class _LlmPort:
    async def reason(self, request, context, memory, pending_state):
        return LifecycleDecision(status=RequestStatus.FAILED)


def create_app(settings: RouterSettings | None = None, *, audio_sink=None):
    settings = settings or RouterSettings.load()
    started = monotonic()
    store = SQLiteObservabilityStore(settings.database_path)
    request_store = RequestStateStore(settings.database_path)
    identity_config = IdentityRuntimeConfigStore(
        settings.database_path,
        settings.identification_timeout_seconds,
    )
    event_broker = InteractionEventBroker(queue_size=settings.websocket_queue_size)
    observability = ObservabilityService(store, request_store=request_store)
    lifecycle = RequestLifecycleService(
        store=request_store,
        broker=event_broker,
        identity_port=_IdentityPort(),
        context_port=_ContextPort(),
        memory_port=_MemoryPort(),
        skill_port=_SkillPort(),
        llm_port=_LlmPort(),
        clarification_timeout_seconds=settings.clarification_timeout_seconds,
        observability=observability,
        identity_config=identity_config,
        identification_timeout_seconds=settings.identification_timeout_seconds,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ready = False
        store.initialize()
        request_store.initialize()
        identity_config.initialize()
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            await app.state.audio_streams.close()

    app = FastAPI(title="Nyra Router", lifespan=lifespan)
    app.state.audio_streams = AudioStreamRegistry(
        audio_sink if audio_sink is not None else SpeakerAudioRelay(settings.speaker_id_stream_url),
        settings.audio_stream_timeout_seconds,
    )
    app.state.settings = settings
    app.state.store = store
    app.state.request_store = request_store
    app.state.identity_config = identity_config
    app.state.observability = observability
    app.state.events = event_broker
    app.state.lifecycle = lifecycle
    app.state.ready = False
    app.state.uptime = lambda: round(monotonic() - started, 3)
    app.include_router(health_router)
    app.include_router(logs_router)
    app.include_router(obs_router)
    app.include_router(requests_router)
    app.include_router(events_router)
    app.include_router(audio_router)
    app.include_router(identity_config_router)
    return app


app = create_app()
