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
from router.api.capabilities import router as capabilities_router
from router.ha_capability import HomeAssistantApiClient, HomeAssistantCapabilityPort
from router.speaker_id_admin import SpeakerIdAdminClient
from router.user_directory import UserDirectory
from router.memory_client import MemoryClient
from router.skills_client import SkillsClient, SkillsUnavailable
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCorrelation,
    SkillExecuteRequest,
    SkillOutcome,
)


class _ContextPort:
    async def resolve(self, request, identity_user_id, trace_id):
        return ContextResult(data={}, semantic_memory_required=False)


class _MemoryPort:
    async def search(self, request, identity_user_id, query, trace_id):
        return {}


class _NoSkillPort:
    async def check(self, request, context, memory, pending_state):
        return SkillMatch(
            matched=False,
            outcome=SkillOutcome.MISS,
        )

    async def execute(self, match, request, context, memory, pending_state):
        return LifecycleDecision.failed("SKILL_NOT_CONFIGURED")


class _RemoteSkillPort:
    def __init__(self, client):
        self.client = client

    @staticmethod
    def _correlation(request, context):
        if context.trace_id is None:
            raise RuntimeError("Skills invocation requires the Router trace")
        return SkillCorrelation(
            request_id=request.request_id,
            origin_request_id=request.origin_request_id,
            trace_id=context.trace_id,
        )

    async def check(self, request, context, memory, pending_state):
        payload = SkillCheckRequest(
            correlation=self._correlation(request, context),
            text=request.input.text,
            language=request.language,
            context=context.data,
            pending_state=pending_state,
        )
        try:
            response = await self.client.check(payload)
        except SkillsUnavailable:
            return SkillMatch(
                matched=False,
                outcome=SkillOutcome.FAILED,
                error_code="SKILLS_UNAVAILABLE",
            )

        if response.outcome is SkillOutcome.MISS:
            return SkillMatch(matched=False, outcome=SkillOutcome.MISS)
        if response.outcome is SkillOutcome.FAILED:
            return SkillMatch(
                matched=False,
                outcome=SkillOutcome.FAILED,
                error_code=(
                    response.error.code
                    if response.error is not None
                    else "SKILLS_FAILED"
                ),
            )
        if response.outcome is SkillOutcome.NEEDS_CLARIFICATION:
            metadata = response.match.metadata if response.match else {}
            text = metadata.get("text")
            pending = metadata.get("pending_state")
            return SkillMatch(
                matched=False,
                outcome=SkillOutcome.NEEDS_CLARIFICATION,
                text=text if isinstance(text, str) else "",
                pending_state=pending if isinstance(pending, dict) else {},
            )
        if response.match is None or not response.match.matched:
            return SkillMatch(
                matched=False,
                outcome=SkillOutcome.FAILED,
                error_code="SKILLS_INVALID_MATCH",
            )
        return SkillMatch(
            matched=True,
            skill_name=response.match.skill_name,
            token=response.match.token,
            memory_requirement=response.match.memory_requirement,
            memory_query=response.match.memory_query,
            outcome=SkillOutcome.HANDLED,
        )

    async def execute(self, match, request, context, memory, pending_state):
        from shared.protocol.skills import SkillMatch as ProtocolSkillMatch

        protocol_match = ProtocolSkillMatch(
            matched=True,
            skill_name=match.skill_name,
            token=match.token,
            memory_requirement=match.memory_requirement,
            memory_query=(
                match.memory_query.query
                if hasattr(match.memory_query, "query")
                else match.memory_query
            ),
        )
        payload = SkillExecuteRequest(
            correlation=self._correlation(request, context),
            match=protocol_match,
            text=request.input.text,
            language=request.language,
            context=context.data,
            memory=memory,
            pending_state=pending_state,
        )
        try:
            response = await self.client.execute(payload)
        except SkillsUnavailable:
            return LifecycleDecision.failed("SKILLS_UNAVAILABLE")

        if response.outcome is SkillOutcome.MISS:
            return LifecycleDecision(
                status=RequestStatus.FAILED,
                llm_fallback=True,
            )
        if response.outcome is SkillOutcome.NEEDS_CLARIFICATION:
            if response.text is None:
                return LifecycleDecision.failed(
                    "SKILLS_INVALID_CLARIFICATION"
                )
            return LifecycleDecision.needs_clarification(
                response.text,
                response.pending_state or {},
            )
        if response.outcome is SkillOutcome.FAILED:
            return LifecycleDecision.failed(
                response.error.code
                if response.error is not None
                else "SKILLS_FAILED"
            )
        return LifecycleDecision.completed(response.text)


class _LlmPort:
    async def reason(self, request, context, memory, pending_state):
        return LifecycleDecision(status=RequestStatus.FAILED)


def create_app(settings: RouterSettings | None = None, *, audio_sink=None, phrase_generator=None,
               wake_word_dataset=None, speaker_id_admin=None, memory_client=None,
               skills_client=None, ha_capability=None):
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
    if skills_client is None and settings.skills_url:
        skills_client = SkillsClient(
            settings.skills_url, timeout=settings.skills_timeout_seconds
        )
    if (
        ha_capability is None
        and settings.home_assistant_url
        and settings.home_assistant_token
    ):
        ha_capability = HomeAssistantCapabilityPort(
            HomeAssistantApiClient(
                settings.home_assistant_url,
                settings.home_assistant_token,
                timeout=settings.home_assistant_timeout_seconds,
            )
        )
    context_port = memory_client if memory_client is not None else _ContextPort()
    memory_port = memory_client if memory_client is not None else _MemoryPort()
    lifecycle = RequestLifecycleService(
        store=request_store,
        broker=event_broker,
        identity_port=audio_relay,
        context_port=context_port,
        memory_port=memory_port,
        skill_port=(
            _RemoteSkillPort(skills_client)
            if skills_client is not None
            else _NoSkillPort()
        ),
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
    app.state.skills_client = skills_client
    app.state.ha_capability = ha_capability
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
    app.include_router(capabilities_router)
    return app


app = create_app()
