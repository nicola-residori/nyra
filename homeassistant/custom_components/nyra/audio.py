from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterable, Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from shared.protocol.ids import validate_prefixed_uuid

from .const import AUDIO_INGRESS_PATH, AUDIO_STREAM_PATH, DOMAIN
from .session import SessionManager, speaker_conversation_key


MAX_JSON_BYTES = 16 * 1024
MAX_CHUNK_BYTES = 256 * 1024


class InvalidAudioIngressStart(ValueError):
    pass


class AudioIngressError(RuntimeError):
    pass


class AudioIngressUnavailable(AudioIngressError):
    pass


class AudioIngressInvalidResponse(AudioIngressError):
    pass


class AudioIngressRejected(AudioIngressError):
    pass


@dataclass(frozen=True)
class IdentificationAudioStart:
    audio_stream_id: str
    session_id: str
    request_id: str
    source_id: str
    language: str
    audio_format: str = "pcm_s16le"
    sample_rate: int = 16000
    channels: int = 1

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "IdentificationAudioStart":
        if value.get("type") not in (None, "START"):
            raise InvalidAudioIngressStart("expected START")
        if value.get("purpose") != "IDENTIFICATION":
            raise InvalidAudioIngressStart("public speaker ingress supports identification only")

        strings: dict[str, str] = {}
        for name in (
            "audio_stream_id",
            "session_id",
            "request_id",
            "source_id",
            "language",
        ):
            item = value.get(name)
            if not isinstance(item, str) or not item.strip() or len(item) > 1024:
                raise InvalidAudioIngressStart(f"invalid {name}")
            strings[name] = item

        try:
            validate_prefixed_uuid(strings["session_id"], "ses")
            validate_prefixed_uuid(strings["request_id"], "req")
        except ValueError as exc:
            raise InvalidAudioIngressStart("invalid correlation ID") from exc

        audio_format = value.get("audio_format", "pcm_s16le")
        sample_rate = value.get("sample_rate", 16000)
        channels = value.get("channels", 1)
        if audio_format not in {"wav", "pcm_s16le"}:
            raise InvalidAudioIngressStart("invalid audio format")
        if type(sample_rate) is not int or not 8000 <= sample_rate <= 96000:
            raise InvalidAudioIngressStart("invalid sample rate")
        if type(channels) is not int or channels not in {1, 2}:
            raise InvalidAudioIngressStart("invalid channel count")

        return cls(
            **strings,
            audio_format=audio_format,
            sample_rate=sample_rate,
            channels=channels,
        )

    def to_wire(self) -> dict[str, Any]:
        return {
            "type": "START",
            "audio_stream_id": self.audio_stream_id,
            "purpose": "IDENTIFICATION",
            "session_id": self.session_id,
            "request_id": self.request_id,
            "source_id": self.source_id,
            "language": self.language,
            "audio_format": self.audio_format,
            "sample_rate": self.sample_rate,
            "channels": self.channels,
        }


def correlate_identification_start(
    value: Mapping[str, Any],
    sessions: SessionManager,
) -> IdentificationAudioStart:
    source_id = value.get("source_id")
    if not isinstance(source_id, str) or not source_id.strip():
        raise InvalidAudioIngressStart("invalid source_id")
    source_id = source_id.strip()
    conversation_key = speaker_conversation_key(source_id)
    correlated = dict(value)
    correlated["source_id"] = source_id
    correlated["session_id"] = sessions.get_or_create_session(conversation_key)
    correlated["request_id"] = sessions.get_request_id(conversation_key)
    return IdentificationAudioStart.from_mapping(correlated)


class JsonBinaryWebSocket(Protocol):
    async def send_json(self, value: dict[str, Any]) -> None: ...
    async def send_bytes(self, value: bytes) -> None: ...
    async def receive_json(self) -> dict[str, Any]: ...
    async def close(self) -> None: ...


ConnectWebSocket = Callable[
    [str, dict[str, str]], Awaitable[JsonBinaryWebSocket]
]


class RouterAudioSession:
    def __init__(
        self,
        websocket: JsonBinaryWebSocket,
        metadata: IdentificationAudioStart,
    ):
        self._websocket = websocket
        self._metadata = metadata
        self._closed = False

    async def async_chunk(self, payload: bytes) -> None:
        if not isinstance(payload, bytes) or not payload:
            raise AudioIngressRejected("audio chunks must be non-empty bytes")
        if len(payload) > MAX_CHUNK_BYTES:
            raise AudioIngressRejected("audio chunk is too large")
        try:
            await self._websocket.send_bytes(payload)
            await self._expect("CHUNK")
        except AudioIngressError:
            raise
        except Exception as exc:
            raise AudioIngressUnavailable("Router audio stream disconnected") from exc

    async def async_end(self) -> dict[str, Any]:
        try:
            await self._websocket.send_json({
                "type": "END",
                "audio_stream_id": self._metadata.audio_stream_id,
            })
            response = await self._expect("RESULT")
            return _validate_identification_result(response.get("result"))
        except AudioIngressError:
            raise
        except Exception as exc:
            raise AudioIngressUnavailable("Router audio stream disconnected") from exc

    async def _expect(self, expected_type: str) -> dict[str, Any]:
        response = await self._websocket.receive_json()
        if not isinstance(response, dict):
            raise AudioIngressInvalidResponse("Router returned a non-object frame")
        if response.get("audio_stream_id") != self._metadata.audio_stream_id:
            raise AudioIngressInvalidResponse("Router returned mismatched stream correlation")
        if response.get("type") == "ERROR" and response.get("outcome") == "FAILED":
            reason = response.get("reason_code")
            raise AudioIngressRejected(reason if isinstance(reason, str) else "STREAM_FAILED")
        if response.get("type") != expected_type:
            raise AudioIngressInvalidResponse(
                f"expected {expected_type}, got {response.get('type')!r}"
            )
        return response

    async def async_close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._websocket.close()
        except Exception:
            pass


class RouterAudioStreamClient:
    def __init__(
        self,
        base_url: str,
        token: str | None,
        connect: ConnectWebSocket,
    ):
        self._url = _websocket_url(base_url)
        self._token = token or None
        self._connect = connect

    @property
    def headers(self) -> dict[str, str]:
        if self._token is None:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    async def async_open(
        self,
        metadata: IdentificationAudioStart,
    ) -> RouterAudioSession:
        websocket = None
        try:
            websocket = await self._connect(self._url, self.headers)
            session = RouterAudioSession(websocket, metadata)
            await websocket.send_json(metadata.to_wire())
            await session._expect("STARTED")
            return session
        except asyncio.CancelledError:
            if websocket is not None:
                try:
                    await websocket.close()
                except Exception:
                    pass
            raise
        except AudioIngressError:
            if websocket is not None:
                try:
                    await websocket.close()
                except Exception:
                    pass
            raise
        except Exception as exc:
            if websocket is not None:
                try:
                    await websocket.close()
                except Exception:
                    pass
            raise AudioIngressUnavailable("Nyra Router audio ingress is unavailable") from exc

    async def async_stream(
        self,
        metadata: IdentificationAudioStart,
        chunks: Iterable[bytes] | AsyncIterable[bytes],
    ) -> dict[str, Any]:
        session = await self.async_open(metadata)
        try:
            if isinstance(chunks, AsyncIterable):
                async for chunk in chunks:
                    await session.async_chunk(chunk)
            else:
                for chunk in chunks:
                    await session.async_chunk(chunk)
            return await session.async_end()
        finally:
            await session.async_close()


def _websocket_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    if url.startswith("https://"):
        url = "wss://" + url[8:]
    elif url.startswith("http://"):
        url = "ws://" + url[7:]
    elif not url.startswith(("ws://", "wss://")):
        raise ValueError("Router URL must use HTTP(S) or WS(S)")
    return url + AUDIO_STREAM_PATH


def _validate_identification_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AudioIngressInvalidResponse("Router returned an invalid result")
    outcome = value.get("outcome")
    user_id = value.get("identified_user_id")
    if outcome not in {"IDENTIFIED", "NOT_RECOGNIZED", "FAILED"}:
        raise AudioIngressInvalidResponse("Router returned an invalid outcome")
    if outcome == "IDENTIFIED":
        if not isinstance(user_id, str) or not user_id or user_id == "guest":
            raise AudioIngressInvalidResponse("Router returned an invalid identity")
    elif user_id is not None:
        raise AudioIngressInvalidResponse("unresolved result exposed an identity")
    return value


class HomeAssistantAudioIngress:
    def __init__(
        self,
        client: RouterAudioStreamClient,
        sessions: SessionManager,
        *,
        timeout_seconds: float = 30.0,
        max_active_streams: int = 32,
    ):
        self.client = client
        self.sessions = sessions
        self.timeout_seconds = timeout_seconds
        self.max_active_streams = max_active_streams
        self._active: dict[Any, RouterAudioSession | None] = {}
        self._stream_ids: dict[Any, str | None] = {}
        self._tasks: set[asyncio.Task] = set()
        self._accepting = True

    async def async_handle(self, websocket) -> None:
        if not self._accepting or len(self._active) >= self.max_active_streams:
            await self._send_error(websocket, None, "CAPACITY_EXCEEDED")
            await websocket.close()
            return
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        self._active[websocket] = None
        self._stream_ids[websocket] = None
        try:
            async with asyncio.timeout(self.timeout_seconds):
                await self._async_relay(websocket)
        except TimeoutError:
            await self._send_error(websocket, self._stream_ids[websocket], "TIMEOUT")
        finally:
            self._stream_ids.pop(websocket, None)
            session = self._active.pop(websocket, None)
            if session is not None:
                await session.async_close()
            await websocket.close()
            if task is not None:
                self._tasks.discard(task)

    async def _async_relay(self, websocket) -> None:
        router_session = None
        stream_id = None
        try:
            frame_type, data = _incoming_frame(await websocket.receive())
            if frame_type != "TEXT":
                raise InvalidAudioIngressStart("first frame must be START JSON")
            metadata = correlate_identification_start(_json_object(data), self.sessions)
            stream_id = metadata.audio_stream_id
            self._stream_ids[websocket] = stream_id
            router_session = await self.client.async_open(metadata)
            self._active[websocket] = router_session
            await websocket.send_json({"type": "STARTED", "audio_stream_id": stream_id})

            while True:
                frame_type, data = _incoming_frame(await websocket.receive())
                if frame_type in {"CLOSE", "CLOSED", "CLOSING", "ERROR"}:
                    return
                if frame_type == "BINARY":
                    await router_session.async_chunk(bytes(data))
                    await websocket.send_json({"type": "CHUNK", "audio_stream_id": stream_id})
                    continue
                if frame_type != "TEXT":
                    raise AudioIngressRejected("unsupported audio ingress frame")
                message = _json_object(data)
                if message != {"type": "END", "audio_stream_id": stream_id}:
                    raise AudioIngressRejected("invalid END frame")
                result = await self._end_or_disconnect(websocket, router_session)
                if result is None:
                    return
                await websocket.send_json({
                    "type": "RESULT",
                    "audio_stream_id": stream_id,
                    "result": result,
                })
                return
        except (InvalidAudioIngressStart, AudioIngressError, ValueError) as exc:
            await self._send_error(websocket, stream_id, _reason_code(exc))

    async def _end_or_disconnect(self, websocket, router_session):
        ending = asyncio.create_task(router_session.async_end())
        receiving = asyncio.create_task(websocket.receive())
        try:
            done, _ = await asyncio.wait(
                {ending, receiving},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if ending in done:
                return await ending
            if receiving in done:
                frame_type, _ = _incoming_frame(receiving.result())
                if frame_type in {"CLOSE", "CLOSED", "CLOSING", "ERROR"}:
                    return None
                raise AudioIngressRejected("frame received after END")
            raise RuntimeError("audio ingress wait completed without a result")
        finally:
            for task in (ending, receiving):
                if not task.done():
                    task.cancel()
            await asyncio.gather(ending, receiving, return_exceptions=True)

    async def _send_error(self, websocket, stream_id, reason_code: str) -> None:
        try:
            await websocket.send_json({
                "type": "ERROR",
                "audio_stream_id": stream_id,
                "outcome": "FAILED",
                "reason_code": reason_code,
            })
        except Exception:
            pass

    async def async_shutdown(self) -> None:
        self._accepting = False
        sessions = [item for item in self._active.values() if item is not None]
        websockets = list(self._active)
        await asyncio.gather(
            *(session.async_close() for session in sessions),
            *(websocket.close() for websocket in websockets),
            return_exceptions=True,
        )
        current = asyncio.current_task()
        tasks = [task for task in self._tasks if task is not current]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def _incoming_frame(frame) -> tuple[str, Any]:
    if isinstance(frame, Mapping):
        frame_type = frame.get("type")
        data = frame.get("data")
    else:
        frame_type = getattr(frame, "type", None)
        data = getattr(frame, "data", None)
    name = getattr(frame_type, "name", frame_type)
    return str(name).upper(), data


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, bytes):
        if len(value) > MAX_JSON_BYTES:
            raise InvalidAudioIngressStart("JSON frame is too large")
        value = value.decode("utf-8")
    if isinstance(value, str):
        if len(value.encode("utf-8")) > MAX_JSON_BYTES:
            raise InvalidAudioIngressStart("JSON frame is too large")
        value = json.loads(value)
    if not isinstance(value, dict):
        raise InvalidAudioIngressStart("JSON frame must be an object")
    return value


def _reason_code(exc: Exception) -> str:
    if isinstance(exc, InvalidAudioIngressStart):
        return "INVALID_START"
    if isinstance(exc, AudioIngressRejected):
        value = str(exc)
        if value.isupper() and " " not in value:
            return value
        return "INVALID_MESSAGE"
    if isinstance(exc, AudioIngressUnavailable):
        return "ROUTER_UNAVAILABLE"
    return "INVALID_MESSAGE"


def authorized_ingress(headers: Mapping[str, str], token: str | None) -> bool:
    if not token:
        return True
    authorization = headers.get("Authorization") or headers.get("authorization")
    return authorization == f"Bearer {token}"


try:
    from homeassistant.components.http import HomeAssistantView
except ImportError:
    class HomeAssistantView:  # type: ignore[no-redef]
        pass


class NyraAudioIngressView(HomeAssistantView):
    url = AUDIO_INGRESS_PATH
    name = "api:nyra:audio"
    requires_auth = False

    def __init__(
        self,
        ingress: HomeAssistantAudioIngress | None,
        token: str | None,
        owner_entry_id: str | None = None,
    ):
        self.owner_entry_id = owner_entry_id
        self.configure(ingress, token)

    def configure(
        self,
        ingress: HomeAssistantAudioIngress | None,
        token: str | None,
    ) -> None:
        self.ingress = ingress
        self.token = token or None
        self.requires_auth = self.token is None

    async def get(self, request):
        from aiohttp import web

        if self.ingress is None:
            raise web.HTTPServiceUnavailable()
        if self.token and not authorized_ingress(request.headers, self.token):
            raise web.HTTPUnauthorized()
        websocket = web.WebSocketResponse(max_msg_size=MAX_CHUNK_BYTES)
        await websocket.prepare(request)
        await self.ingress.async_handle(websocket)
        return websocket


def register_audio_ingress_view(
    hass,
    ingress: HomeAssistantAudioIngress,
    token: str | None,
    *,
    owner_entry_id: str | None = None,
) -> NyraAudioIngressView:
    domain_data = hass.data.setdefault(DOMAIN, {})
    existing = domain_data.get("audio_ingress_view")
    if isinstance(existing, NyraAudioIngressView):
        if (
            owner_entry_id is not None
            and existing.owner_entry_id is not None
            and existing.owner_entry_id != owner_entry_id
        ):
            raise RuntimeError("Nyra audio ingress is already owned by another entry")
        existing.owner_entry_id = owner_entry_id or existing.owner_entry_id
        existing.configure(ingress, token)
        return existing
    view = NyraAudioIngressView(ingress, token, owner_entry_id)
    hass.http.register_view(view)
    domain_data["audio_ingress_view"] = view
    return view


def disable_audio_ingress_view(hass, view: NyraAudioIngressView) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    if domain_data.get("audio_ingress_view") is view:
        view.configure(None, None)
        view.owner_entry_id = None
