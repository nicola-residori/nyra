from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from shared.protocol.events import (
    EventCategory,
    IdentityFeedbackEvent,
    InteractionStateChanged,
    SessionClosedEvent,
)

from .const import EVENTS_PATH
from .speaker import SpeakerStateMachine

_LOGGER = logging.getLogger(__name__)


class JsonWebSocket(Protocol):
    async def send_json(self, data: dict[str, Any]) -> None: ...
    async def receive_json(self) -> dict[str, Any]: ...
    async def close(self) -> None: ...


ConnectWebSocket = Callable[[str, dict[str, str]], Awaitable[JsonWebSocket]]


class RouterEventClient:
    def __init__(self, base_url: str, token: str | None, connect: ConnectWebSocket, speaker: SpeakerStateMachine):
        self._url = self._to_ws_url(base_url)
        self._token = token or None
        self._connect = connect
        self._speaker = speaker
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    @staticmethod
    def _to_ws_url(base_url: str) -> str:
        url = base_url.rstrip("/")
        if url.startswith("https://"):
            url = "wss://" + url[8:]
        elif url.startswith("http://"):
            url = "ws://" + url[7:]
        return url + EVENTS_PATH

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._stopped.clear()
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        delay = 1.0
        while not self._stopped.is_set():
            ws = None
            try:
                ws = await self._connect(self._url, self.headers)
                await ws.send_json({
                    "action": "subscribe",
                    "categories": [
                        EventCategory.INTERACTION_STATE.value,
                        EventCategory.IDENTITY.value,
                        EventCategory.SESSION.value,
                    ],
                })
                await ws.send_json({"action": "resync"})
                delay = 1.0
                while not self._stopped.is_set():
                    message = await ws.receive_json()
                    await self.handle_message(message, ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # transport must self-heal without killing HA
                _LOGGER.warning("Nyra Router event stream disconnected: %s", exc)
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                delay = min(delay * 2, 30.0)
            finally:
                if ws is not None:
                    try:
                        await ws.close()
                    except Exception:
                        pass

    async def handle_message(self, message: dict[str, Any], ws: JsonWebSocket | None = None) -> None:
        if message.get("type") == "ping":
            if ws is not None:
                await ws.send_json({"action": "ping"})
            return
        if message.get("type") in {"subscribed", "pong", "state_snapshot", "error"}:
            if message.get("type") == "state_snapshot":
                for state in message.get("states", []):
                    try:
                        event = InteractionStateChanged.model_validate({
                            "state": state["state"],
                            "source": {"id": state["source_id"]} if state.get("source_id") else None,
                            "session_id": state.get("session_id"),
                            "request_id": state.get("request_id"),
                            "trace_id": state.get("trace_id"),
                            "timestamp": state.get("timestamp"),
                        })
                        await self._speaker.handle_state(event)
                    except Exception as exc:
                        _LOGGER.debug("Ignoring invalid Nyra state snapshot: %s", exc)
            return

        try:
            event_name = message.get("event")
            if event_name == "INTERACTION_STATE_CHANGED":
                await self._speaker.handle_state(InteractionStateChanged.model_validate(message))
            elif event_name == "IDENTITY_FEEDBACK":
                await self._speaker.handle_identity(IdentityFeedbackEvent.model_validate(message))
            elif event_name == "SESSION_CLOSED":
                await self._speaker.handle_session_closed(SessionClosedEvent.model_validate(message))
        except Exception as exc:
            _LOGGER.warning("Ignoring invalid Nyra event: %s", exc)
