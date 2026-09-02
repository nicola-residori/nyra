from __future__ import annotations

from dataclasses import dataclass

from .protocol_bootstrap import ensure_shared_protocol

ensure_shared_protocol()

from .client import NyraRouterClient
from .const import CONF_INGRESS_TOKEN, CONF_ROUTER_URL, DEFAULT_SESSION_TTL_SECONDS, DOMAIN
from .events import RouterEventClient
from .session import SessionManager
from .speaker import SpeakerStateMachine


@dataclass
class NyraRuntime:
    client: NyraRouterClient
    sessions: SessionManager
    speaker: SpeakerStateMachine
    events: RouterEventClient

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
    entry.runtime_data = NyraRuntime(
        client,
        SessionManager(DEFAULT_SESSION_TTL_SECONDS),
        speaker,
        event_client,
        register_speaking_restore_listener(hass, speaker),
    )
    await event_client.start()
    await hass.config_entries.async_forward_entry_setups(
        entry,
        [Platform.CONVERSATION],
    )
    return True


async def async_unload_entry(hass, entry) -> bool:
    from homeassistant.const import Platform

    runtime = entry.runtime_data
    unregister_speaking_restore_listener(runtime)
    await runtime.events.stop()
    unloaded = await hass.config_entries.async_unload_platforms(
        entry,
        [Platform.CONVERSATION],
    )
    await runtime.client.async_close()
    return unloaded
