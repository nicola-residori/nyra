from __future__ import annotations

from dataclasses import dataclass

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


async def async_setup_entry(hass, entry) -> bool:
    from homeassistant.const import Platform
    from homeassistant.exceptions import ConfigEntryNotReady
    from homeassistant.helpers.aiohttp_client import async_get_clientsession
    from homeassistant.helpers.httpx_client import get_async_client

    from .esphome import EspHomeSpeakerOutput

    client = NyraRouterClient(
        entry.data[CONF_ROUTER_URL],
        entry.data.get(CONF_INGRESS_TOKEN) or None,
        client=get_async_client(hass),
    )
    if not await client.async_ready():
        raise ConfigEntryNotReady("Nyra Router is not ready")

    # Real source->entity mappings are bound during deployment to the actual speakers.
    output = EspHomeSpeakerOutput({}, lambda domain, service, data: hass.services.async_call(domain, service, data, blocking=False))
    speaker = SpeakerStateMachine(output)
    aiohttp_session = async_get_clientsession(hass)

    async def connect(url, headers):
        return await aiohttp_session.ws_connect(url, headers=headers)

    event_client = RouterEventClient(entry.data[CONF_ROUTER_URL], entry.data.get(CONF_INGRESS_TOKEN), connect, speaker)
    entry.runtime_data = NyraRuntime(client, SessionManager(DEFAULT_SESSION_TTL_SECONDS), speaker, event_client)
    await event_client.start()
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.CONVERSATION])
    return True


async def async_unload_entry(hass, entry) -> bool:
    from homeassistant.const import Platform

    runtime = entry.runtime_data
    await runtime.events.stop()
    unloaded = await hass.config_entries.async_unload_platforms(entry, [Platform.CONVERSATION])
    await runtime.client.async_close()
    return unloaded
