from __future__ import annotations

from dataclasses import dataclass

from .protocol_bootstrap import ensure_shared_protocol

ensure_shared_protocol()

from .client import NyraRouterClient
from .audio import (
    HomeAssistantAudioIngress,
    RouterAudioStreamClient,
    disable_audio_ingress_view,
    register_audio_ingress_view,
)
from .const import CONF_INGRESS_TOKEN, CONF_ROUTER_URL, DEFAULT_SESSION_TTL_SECONDS, DOMAIN
from .events import RouterEventClient
from .session import SessionManager
from .speaker import SpeakerStateMachine
from .enrollment import (
    EnrollmentCoordinator,
    localized_enrollment_message,
    register_enrollment_services,
    unregister_enrollment_services,
)
from .panel import async_register_enrollment_panel, async_unregister_enrollment_panel
from .wake_word_capture import WakeWordCaptureCoordinator


@dataclass
class NyraRuntime:
    client: NyraRouterClient
    sessions: SessionManager
    speaker: SpeakerStateMachine
    events: RouterEventClient
    audio_client: RouterAudioStreamClient
    audio_ingress: HomeAssistantAudioIngress
    audio_ingress_view: object | None
    enrollment: EnrollmentCoordinator
    wake_word_capture: WakeWordCaptureCoordinator
    enrollment_panel_registered: bool = False

    speaking_restore_unsubscribe: object | None = None



def register_speaking_restore_listener(hass, speaker: SpeakerStateMachine):
    """Give actual local playback priority over Router semantic visuals."""

    def source_id_from(event) -> str | None:
        source_id = event.data.get("source_id")
        if not isinstance(source_id, str):
            return None
        source_id = source_id.strip()
        return source_id or None

    async def handle_speaking_started(event) -> None:
        source_id = source_id_from(event)
        if source_id:
            await speaker.begin_speaking(source_id)

    async def handle_speaking_ended(event) -> None:
        source_id = source_id_from(event)
        if source_id:
            await speaker.end_speaking(source_id)

    unsubscribe_started = hass.bus.async_listen(
        "esphome.nyra_speaking_started",
        handle_speaking_started,
    )
    unsubscribe_ended = hass.bus.async_listen(
        "esphome.nyra_speaking_ended",
        handle_speaking_ended,
    )

    def unsubscribe() -> None:
        unsubscribe_started()
        unsubscribe_ended()

    return unsubscribe


def unregister_speaking_restore_listener(runtime: NyraRuntime) -> None:
    unsubscribe = runtime.speaking_restore_unsubscribe
    if unsubscribe is None:
        return
    runtime.speaking_restore_unsubscribe = None
    unsubscribe()


async def unregister_audio_ingress(hass, runtime: NyraRuntime) -> None:
    view = runtime.audio_ingress_view
    if view is not None:
        runtime.audio_ingress_view = None
        disable_audio_ingress_view(hass, view)
    await runtime.audio_ingress.async_shutdown()


async def async_setup_entry(hass, entry) -> bool:
    from homeassistant.const import Platform
    from homeassistant.exceptions import ConfigEntryNotReady
    from homeassistant.helpers import device_registry as dr, entity_registry as er
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    from homeassistant.helpers.httpx_client import get_async_client

    from .esphome import (
        SOURCE_ID_NAME,
        EspHomeSpeakerOutput,
        discover_speaker_targets,
    )

    client = NyraRouterClient(
        entry.data[CONF_ROUTER_URL],
        entry.data.get(CONF_INGRESS_TOKEN) or None,
        client=get_async_client(hass),
    )
    if not await client.async_ready():
        raise ConfigEntryNotReady("Nyra Router is not ready")

    async def resolve_speaker_targets():
        device_registry = dr.async_get(hass)
        entity_registry = er.async_get(hass)
        source_states = {
            entity.entity_id: state.state
            for entity in entity_registry.entities.values()
            if entity.platform == "esphome"
            and entity.original_name == SOURCE_ID_NAME
            and (state := hass.states.get(entity.entity_id)) is not None
        }
        return discover_speaker_targets(
            device_registry.devices.values(),
            entity_registry.entities.values(),
            source_states,
        )

    targets = await resolve_speaker_targets()
    output = EspHomeSpeakerOutput(
        targets,
        lambda domain, service, data: hass.services.async_call(
            domain,
            service,
            data,
            blocking=False,
        ),
        resolve_targets=resolve_speaker_targets,
    )
    speaker = SpeakerStateMachine(output)
    aiohttp_session = async_get_clientsession(hass)

    async def connect(url, headers):
        return await aiohttp_session.ws_connect(url, headers=headers)

    event_client = RouterEventClient(
        entry.data[CONF_ROUTER_URL],
        entry.data.get(CONF_INGRESS_TOKEN),
        connect,
        speaker,
    )
    sessions = SessionManager(DEFAULT_SESSION_TTL_SECONDS)
    audio_client = RouterAudioStreamClient(
        entry.data[CONF_ROUTER_URL],
        entry.data.get(CONF_INGRESS_TOKEN),
        connect,
    )

    async def enrollment_updated(session):
        hass.bus.async_fire("nyra_enrollment_updated", session)
        source_id = session["source_id"]
        status = session["status"]
        if status == "COMPLETED":
            await output.announce(
                source_id,
                localized_enrollment_message(session["language"], status),
            )
        elif status == "TERMINATED":
            await output.close_feedback(source_id)

    enrollment = EnrollmentCoordinator(
        client,
        on_update=enrollment_updated,
        record_output=output,
    )
    async def wake_word_updated(session):
        hass.bus.async_fire("nyra_wake_word_capture_updated", session)

    wake_word_capture = WakeWordCaptureCoordinator(
        client, on_update=wake_word_updated, record_output=output
    )
    await enrollment.async_restore(targets.keys())
    async def current_source_ids():
        return (await resolve_speaker_targets()).keys()

    await async_register_enrollment_panel(
        hass, enrollment, current_source_ids, wake_word_capture
    )
    audio_ingress = HomeAssistantAudioIngress(
        audio_client, sessions, enrollment=enrollment, wake_word=wake_word_capture
    )
    audio_ingress_view = register_audio_ingress_view(
        hass,
        audio_ingress,
        entry.data.get(CONF_INGRESS_TOKEN),
        owner_entry_id=entry.entry_id,
    )
    entry.runtime_data = NyraRuntime(
        client=client,
        sessions=sessions,
        speaker=speaker,
        events=event_client,
        audio_client=audio_client,
        audio_ingress=audio_ingress,
        audio_ingress_view=audio_ingress_view,
        enrollment=enrollment,
        wake_word_capture=wake_word_capture,
        enrollment_panel_registered=True,
        speaking_restore_unsubscribe=register_speaking_restore_listener(hass, speaker),
    )
    register_enrollment_services(hass, enrollment)
    await event_client.start()
    await hass.config_entries.async_forward_entry_setups(
        entry,
        [Platform.CONVERSATION],
    )
    return True


async def async_unload_entry(hass, entry) -> bool:
    from homeassistant.const import Platform

    runtime = entry.runtime_data
    if runtime.enrollment_panel_registered:
        async_unregister_enrollment_panel(hass)
        runtime.enrollment_panel_registered = False
    unregister_enrollment_services(hass)
    unregister_speaking_restore_listener(runtime)
    await unregister_audio_ingress(hass, runtime)
    await runtime.events.stop()
    unloaded = await hass.config_entries.async_unload_platforms(
        entry,
        [Platform.CONVERSATION],
    )
    await runtime.client.async_close()
    return unloaded
