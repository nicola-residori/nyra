from __future__ import annotations

from pathlib import Path
import inspect
from typing import Any

from .enrollment import EnrollmentConflict, EnrollmentUnauthorized
from .users import authenticated_user_reference, async_sync_user_reference


PANEL_URL_PATH = "nyra-enrollment"
PANEL_ELEMENT = "nyra-enrollment-panel"
PANEL_ASSET_URL = "/api/nyra/frontend/nyra-enrollment-panel.js"


def _user_id(connection) -> str:
    try:
        return authenticated_user_reference(connection.user).user_id
    except (AttributeError, ValueError):
        raise EnrollmentUnauthorized("Autenticazione Home Assistant richiesta.")


async def _sync_connection_user(connection, coordinator):
    try:
        reference = authenticated_user_reference(connection.user)
    except (AttributeError, ValueError):
        raise EnrollmentUnauthorized("Autenticazione Home Assistant richiesta.")
    await async_sync_user_reference(getattr(coordinator, "client", None), reference)
    return reference


def _send_error(connection, message_id: int, exc: Exception) -> None:
    if isinstance(exc, EnrollmentUnauthorized):
        code = "unauthorized"
    elif isinstance(exc, EnrollmentConflict):
        code = "enrollment_conflict"
    else:
        code = "enrollment_failed"
    connection.send_error(message_id, code, str(exc))


async def ws_state(hass, connection, msg, coordinator, source_ids) -> None:
    try:
        reference = await _sync_connection_user(connection, coordinator)
        user_id = reference.user_id
        sources = source_ids() if callable(source_ids) else source_ids
        if inspect.isawaitable(sources):
            sources = await sources
        sources = sorted(set(sources))
        await coordinator.async_restore(sources)
        connection.send_result(msg["id"], {
            "sources": sources,
            "sessions": coordinator.state_for_user(user_id),
        })
    except Exception as exc:
        _send_error(connection, msg["id"], exc)


async def ws_start(hass, connection, msg, coordinator) -> None:
    try:
        reference = await _sync_connection_user(connection, coordinator)
        result = await coordinator.async_start(
            authenticated_user_id=reference.user_id,
            source_id=msg["source_id"],
            language=msg.get("language", "it-IT"),
            target_count=msg.get("sample_count", 6),
        )
        connection.send_result(msg["id"], result)
    except Exception as exc:
        _send_error(connection, msg["id"], exc)


async def ws_record(hass, connection, msg, coordinator) -> None:
    try:
        result = await coordinator.async_record(
            _user_id(connection), msg["session_id"]
        )
        connection.send_result(msg["id"], result)
    except Exception as exc:
        _send_error(connection, msg["id"], exc)


async def ws_terminate(hass, connection, msg, coordinator) -> None:
    try:
        result = await coordinator.async_terminate(
            _user_id(connection), msg["session_id"], "user_cancelled"
        )
        connection.send_result(msg["id"], result)
    except Exception as exc:
        _send_error(connection, msg["id"], exc)


async def ws_wake_word_state(hass, connection, msg, coordinator, source_ids) -> None:
    try:
        reference = await _sync_connection_user(connection, coordinator)
        user_id = reference.user_id
        sources = source_ids() if callable(source_ids) else source_ids
        if inspect.isawaitable(sources):
            sources = await sources
        sources = sorted(set(sources))
        await coordinator.async_restore(sources)
        connection.send_result(msg["id"], {
            "sources": sources,
            "sessions": coordinator.state_for_user(user_id),
        })
    except Exception as exc:
        _send_error(connection, msg["id"], exc)


async def ws_capture_wake_word(hass, connection, msg, coordinator) -> None:
    try:
        reference = await _sync_connection_user(connection, coordinator)
        result = await coordinator.async_capture(
            authenticated_user_id=reference.user_id,
            source_id=msg["source_id"],
            language=msg.get("language", "it-IT"),
            wake_word_text=msg["wake_word_text"],
        )
        connection.send_result(msg["id"], result)
    except Exception as exc:
        _send_error(connection, msg["id"], exc)


async def ws_wake_word_sample_count(hass, connection, msg, coordinator) -> None:
    try:
        _user_id(connection)
        result = await coordinator.client.async_wake_word_sample_count(
            msg["wake_word_text"]
        )
        connection.send_result(msg["id"], {"sample_count": result})
    except Exception as exc:
        _send_error(connection, msg["id"], exc)


async def async_register_enrollment_panel(
    hass, coordinator, source_ids, wake_word_coordinator=None
) -> None:
    import voluptuous as vol
    from homeassistant.components import panel_custom, websocket_api
    from homeassistant.components.http import StaticPathConfig

    frontend_path = Path(__file__).parent / "frontend" / "nyra-enrollment-panel.js"
    await hass.http.async_register_static_paths([
        StaticPathConfig(PANEL_ASSET_URL, str(frontend_path), False)
    ])

    @websocket_api.websocket_command({vol.Required("type"): "nyra/enrollment/state"})
    @websocket_api.async_response
    async def handle_state(hass, connection, msg):
        await ws_state(hass, connection, msg, coordinator, source_ids)

    @websocket_api.websocket_command({
        vol.Required("type"): "nyra/enrollment/start",
        vol.Required("source_id"): str,
        vol.Optional("language", default="it-IT"): str,
        vol.Optional("sample_count", default=6): vol.All(int, vol.Range(min=1, max=24)),
    })
    @websocket_api.async_response
    async def handle_start(hass, connection, msg):
        await ws_start(hass, connection, msg, coordinator)

    @websocket_api.websocket_command({
        vol.Required("type"): "nyra/enrollment/record",
        vol.Required("session_id"): str,
    })
    @websocket_api.async_response
    async def handle_record(hass, connection, msg):
        await ws_record(hass, connection, msg, coordinator)

    @websocket_api.websocket_command({
        vol.Required("type"): "nyra/enrollment/terminate",
        vol.Required("session_id"): str,
    })
    @websocket_api.async_response
    async def handle_terminate(hass, connection, msg):
        await ws_terminate(hass, connection, msg, coordinator)

    @websocket_api.websocket_command({vol.Required("type"): "nyra/wake-word/state"})
    @websocket_api.async_response
    async def handle_wake_word_state(hass, connection, msg):
        await ws_wake_word_state(
            hass, connection, msg, wake_word_coordinator, source_ids
        )

    @websocket_api.websocket_command({
        vol.Required("type"): "nyra/wake-word/capture",
        vol.Required("source_id"): str,
        vol.Required("wake_word_text"): str,
        vol.Optional("language", default="it-IT"): str,
    })
    @websocket_api.async_response
    async def handle_wake_word_capture(hass, connection, msg):
        await ws_capture_wake_word(hass, connection, msg, wake_word_coordinator)

    @websocket_api.websocket_command({
        vol.Required("type"): "nyra/wake-word/sample-count",
        vol.Required("wake_word_text"): str,
    })
    @websocket_api.async_response
    async def handle_wake_word_sample_count(hass, connection, msg):
        await ws_wake_word_sample_count(hass, connection, msg, wake_word_coordinator)

    commands = [handle_state, handle_start, handle_record, handle_terminate]
    if wake_word_coordinator is not None:
        commands.extend((
            handle_wake_word_state, handle_wake_word_capture,
            handle_wake_word_sample_count,
        ))
    for command in commands:
        websocket_api.async_register_command(hass, command)

    await panel_custom.async_register_panel(
        hass,
        webcomponent_name=PANEL_ELEMENT,
        sidebar_title="Configurazione Nyra",
        sidebar_icon="mdi:tune-variant",
        frontend_url_path=PANEL_URL_PATH,
        module_url=f"{PANEL_ASSET_URL}?v={int(frontend_path.stat().st_mtime)}",
        config={},
        config_panel_domain="nyra",
        require_admin=False,
    )


def async_unregister_enrollment_panel(hass) -> None:
    from homeassistant.components import frontend

    frontend.async_remove_panel(hass, PANEL_URL_PATH)
