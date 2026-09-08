from contextlib import asynccontextmanager
from time import monotonic
from fastapi import FastAPI
from router.config import RouterSettings
from router.audio_streaming import (
    AudioStreamRegistry,
    CorrelatedIdentityAudioSink,
    SpeakerAudioRelay,
)
from router.storage.sqlite import SQLiteObservabilityStore
from router.observability.service import ObservabilityService
from router.lifecycle.events import InteractionEventBroker
from router.lifecycle.service import RequestLifecycleService, ContextResult, SkillMatch, LifecycleDecision
from router.lifecycle.store import RequestStateStore
from router.identity_config import IdentityRuntimeConfigStore
from router.enrollment import EnrollmentService, EnrollmentSessionStore
from router.wake_word_capture import (
    SpeakerWakeWordDatasetClient, WakeWordCaptureService,
    WakeWordCaptureSessionStore, speaker_id_http_url,
)
from shared.protocol.requests import RequestStatus
from router.api.health import router as health_router
from router.api.logs import router as logs_router
from router.api.observability import router as obs_router
from router.api.requests import router as requests_router
from router.api.audio import router as audio_router
from router.api.events import router as events_router
from router.api.identity_config import router as identity_config_router
from router.api.enrollments import router as enrollments_router
from router.api.wake_word_captures import router as wake_word_captures_router
from router.api.speaker_id_admin import router as speaker_id_admin_router
from router.api.users import router as users_router
from router.api.memory_admin import router as memory_admin_router
from router.speaker_id_admin import SpeakerIdAdminClient
from router.user_directory import UserDirectory
from router.identity_skill import IdentityQuerySkill
from router.memory_client import MemoryClient


class _ContextPort:
    async def resolve(self, request, identity_user_id, trace_id):
        return ContextResult(data={}, semantic_memory_required=False)


class _MemoryPort:
    async def search(self, request, identity_user_id, query, trace_id):
        return {}


class _SkillPort(IdentityQuerySkill):
    pass


class _LlmPort:
    async def reason(self, request, context, memory, pending_state):
        return LifecycleDecision(status=RequestStatus.FAILED)


def create_app(settings: RouterSettings | None = None, *, audio_sink=None, phrase_generator=None,
               wake_word_dataset=None, speaker_id_admin=None, memory_client=None):
    settings = settings or RouterSettings.load()
    started = monotonic()
    store = SQLiteObservabilityStore(settings.database_path)
    request_store = RequestStateStore(settings.database_path)
    observability = ObservabilityService(store, request_store=request_store)
    identity_config = IdentityRuntimeConfigStore(
        settings.database_path,
        settings.identification_timeout_seconds,
    )
    enrollment_store = EnrollmentSessionStore(settings.database_path)
    enrollments = EnrollmentService(
        enrollment_store, phrase_generator=phrase_generator, event_sink=observability
    )
    wake_word_capture_store = WakeWordCaptureSessionStore(settings.database_path)
    wake_word_captures = WakeWordCaptureService(
        wake_word_capture_store, event_sink=observability
    )
    user_directory = UserDirectory(settings.database_path)
    wake_word_dataset = wake_word_dataset or SpeakerWakeWordDatasetClient(
        speaker_id_http_url(settings.speaker_id_http_url, settings.speaker_id_stream_url)
    )
    speaker_id_admin = speaker_id_admin or SpeakerIdAdminClient(
        speaker_id_http_url(settings.speaker_id_http_url, settings.speaker_id_stream_url)
    )
    event_broker = InteractionEventBroker(queue_size=settings.websocket_queue_size)
    audio_relay = CorrelatedIdentityAudioSink(
        audio_sink if audio_sink is not None else SpeakerAudioRelay(settings.speaker_id_stream_url),
        wait_timeout_seconds=settings.audio_stream_timeout_seconds,
        event_sink=observability,
    )
    if memory_client is None and settings.memory_url:
        memory_client = MemoryClient(
            settings.memory_url, timeout=settings.memory_timeout_seconds
        )
    context_port = memory_client if memory_client is not None else _ContextPort()
    memory_port = memory_client if memory_client is not None else _MemoryPort()
    lifecycle = RequestLifecycleService(
        store=request_store,
        broker=event_broker,
        identity_port=audio_relay,
        context_port=context_port,
        memory_port=memory_port,
        skill_port=_SkillPort(),
        llm_port=_LlmPort(),
        clarification_timeout_seconds=settings.clarification_timeout_seconds,
        observability=observability,
        identity_config=identity_config,
        identification_timeout_seconds=settings.identification_timeout_seconds,
        user_directory=user_directory,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ready = False
        store.initialize()
        request_store.initialize()
        identity_config.initialize()
        enrollment_store.initialize()
        wake_word_capture_store.initialize()
        user_directory.initialize()
        app.state.ready = True
        try:
            yield
        finally:
            app.state.ready = False
            await app.state.audio_streams.close()

    app = FastAPI(title="Nyra Router", lifespan=lifespan)
    app.state.audio_streams = AudioStreamRegistry(
        audio_relay, settings.audio_stream_timeout_seconds
    )
    app.state.settings = settings
    app.state.store = store
    app.state.request_store = request_store
    app.state.identity_config = identity_config
    app.state.enrollment_store = enrollment_store
    app.state.enrollments = enrollments
    app.state.wake_word_capture_store = wake_word_capture_store
    app.state.wake_word_captures = wake_word_captures
    app.state.user_directory = user_directory
    app.state.wake_word_dataset = wake_word_dataset
    app.state.speaker_id_admin = speaker_id_admin
    app.state.memory_client = memory_client
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
    app.include_router(enrollments_router)
    app.include_router(wake_word_captures_router)
    app.include_router(speaker_id_admin_router)
    app.include_router(users_router)
    app.include_router(memory_admin_router)
    return app


app = create_app()
