from __future__ import annotations

import asyncio
import importlib

import pytest

from shared.protocol.ids import new_request_id, new_session_id
from homeassistant.custom_components.nyra.conversation import AdapterInput, build_request
from homeassistant.custom_components.nyra.session import SessionManager, speaker_conversation_key


def audio():
    return importlib.import_module("homeassistant.custom_components.nyra.audio")


class RouterWebSocket:
    def __init__(self, *, fail_on_chunk: bool = False):
        self.fail_on_chunk = fail_on_chunk
        self.sent = []
        self.responses = []
        self.closed = False

    async def send_json(self, value):
        self.sent.append(("json", value))
        if value["type"] == "START":
            self.responses.append({
                "type": "STARTED",
                "audio_stream_id": value["audio_stream_id"],
            })
        elif value["type"] == "END":
            self.responses.append({
                "type": "RESULT",
                "audio_stream_id": value["audio_stream_id"],
                "result": {
                    "outcome": "NOT_RECOGNIZED",
                    "identified_user_id": None,
                    "best_score": 0.31,
                    "diagnostic_id": "diag-1",
                    "reason_code": "BELOW_THRESHOLD",
                },
            })

    async def send_bytes(self, value):
        if self.fail_on_chunk:
            raise ConnectionError("router disconnected")
        self.sent.append(("bytes", value))
        stream_id = self.sent[0][1]["audio_stream_id"]
        self.responses.append({"type": "CHUNK", "audio_stream_id": stream_id})

    async def receive_json(self):
        return self.responses.pop(0)

    async def close(self):
        self.closed = True


def identification_start(**changes):
    values = {
        "audio_stream_id": "audio-a",
        "session_id": new_session_id(),
        "request_id": new_request_id(),
        "source_id": "speaker-kitchen",
        "language": "en-US",
        "audio_format": "pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
    }
    values.update(changes)
    return audio().IdentificationAudioStart(**values)


@pytest.mark.asyncio
async def test_audio_ingress_streams_to_router_without_claiming_human_identity():
    socket = RouterWebSocket()
    connections = []

    async def connect(url, headers):
        connections.append((url, headers))
        return socket

    client = audio().RouterAudioStreamClient(
        "https://router.example:8090/",
        "secret",
        connect,
    )
    result = await client.async_stream(
        identification_start(),
        [b"one", b"two"],
    )

    assert connections == [(
        "wss://router.example:8090/v1/audio/stream",
        {"Authorization": "Bearer secret"},
    )]
    start = socket.sent[0][1]
    assert start == {
        "type": "START",
        "audio_stream_id": "audio-a",
        "purpose": "IDENTIFICATION",
        "session_id": start["session_id"],
        "request_id": start["request_id"],
        "source_id": "speaker-kitchen",
        "language": "en-US",
        "audio_format": "pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
    }
    assert "identity" not in start
    assert "user_id" not in start
    assert socket.sent[1:] == [
        ("bytes", b"one"),
        ("bytes", b"two"),
        ("json", {"type": "END", "audio_stream_id": "audio-a"}),
    ]
    assert result["outcome"] == "NOT_RECOGNIZED"
    assert socket.closed


@pytest.mark.asyncio
async def test_audio_ingress_applies_backpressure_before_reading_next_chunk():
    socket = RouterWebSocket()
    released = asyncio.Event()
    produced = []

    original_receive = socket.receive_json

    async def receive_json():
        response = await original_receive()
        if response["type"] == "CHUNK" and len(produced) == 1:
            released.set()
        return response

    socket.receive_json = receive_json

    async def chunks():
        produced.append("one")
        yield b"one"
        assert released.is_set()
        produced.append("two")
        yield b"two"

    client = audio().RouterAudioStreamClient(
        "http://router:8090",
        None,
        lambda url, headers: asyncio.sleep(0, result=socket),
    )
    await client.async_stream(identification_start(), chunks())

    assert produced == ["one", "two"]


@pytest.mark.asyncio
async def test_audio_ingress_transport_failure_closes_without_retry():
    socket = RouterWebSocket(fail_on_chunk=True)
    calls = 0

    async def connect(url, headers):
        nonlocal calls
        calls += 1
        return socket

    client = audio().RouterAudioStreamClient("http://router:8090", None, connect)

    with pytest.raises(audio().AudioIngressUnavailable):
        await client.async_stream(identification_start(), [b"audio"])

    assert calls == 1
    assert socket.closed


@pytest.mark.asyncio
async def test_audio_open_cancellation_closes_acquired_router_socket():
    socket = RouterWebSocket()
    waiting = asyncio.Event()

    async def receive_json():
        waiting.set()
        await asyncio.Event().wait()

    socket.receive_json = receive_json
    client = audio().RouterAudioStreamClient(
        "http://router:8090",
        None,
        lambda url, headers: asyncio.sleep(0, result=socket),
    )
    task = asyncio.create_task(client.async_open(identification_start()))
    await waiting.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert socket.closed


def test_ingress_replaces_untrusted_ids_with_ha_session_correlation():
    sessions = SessionManager()
    supplied_session = new_session_id()
    supplied_request = new_request_id()
    parsed = audio().correlate_identification_start({
        **identification_start().to_wire(),
        "session_id": supplied_session,
        "request_id": supplied_request,
    }, sessions)

    conversation_key = speaker_conversation_key("speaker-kitchen")
    request = build_request(
        AdapterInput(
            "ciao",
            "it-IT",
            conversation_key,
            satellite_id="assist_satellite.kitchen",
            nyra_source_id="speaker-kitchen",
        ),
        sessions,
    )

    assert parsed.session_id == request.session_id
    assert parsed.request_id == request.request_id
    assert parsed.session_id != supplied_session
    assert parsed.request_id != supplied_request


def test_concurrent_sources_receive_isolated_ha_correlation():
    sessions = SessionManager()
    starts = [
        audio().correlate_identification_start(
            identification_start(
                audio_stream_id=f"audio-{source}",
                source_id=f"speaker-{source}",
            ).to_wire(),
            sessions,
        )
        for source in ("kitchen", "bedroom")
    ]

    assert starts[0].session_id != starts[1].session_id
    assert starts[0].request_id != starts[1].request_id
    for start in starts:
        request = build_request(
            AdapterInput(
                "ciao",
                "it-IT",
                speaker_conversation_key(start.source_id),
                satellite_id=f"assist_satellite.{start.source_id}",
                nyra_source_id=start.source_id,
            ),
            sessions,
        )
        assert (start.session_id, start.request_id) == (
            request.session_id,
            request.request_id,
        )


def test_public_ingress_accepts_identification_metadata_only():
    parsed = audio().IdentificationAudioStart.from_mapping({
        "type": "START",
        "audio_stream_id": "audio-a",
        "purpose": "IDENTIFICATION",
        "session_id": new_session_id(),
        "request_id": new_request_id(),
        "source_id": "speaker-a",
        "language": "it-IT",
        "audio_format": "pcm_s16le",
        "sample_rate": 16000,
        "channels": 1,
        "user_id": "untrusted-device-claim",
    })

    assert parsed.source_id == "speaker-a"
    assert not hasattr(parsed, "user_id")
    with pytest.raises(audio().InvalidAudioIngressStart):
        audio().IdentificationAudioStart.from_mapping({
            "type": "START",
            "audio_stream_id": "audio-b",
            "purpose": "ENROLLMENT",
            "session_id": new_session_id(),
            "request_id": new_request_id(),
            "source_id": "speaker-a",
            "language": "it-IT",
        })


def test_ingress_token_is_checked_without_reusing_ha_user_identity():
    assert audio().authorized_ingress(
        {"Authorization": "Bearer ingress-secret"},
        "ingress-secret",
    )
    assert not audio().authorized_ingress({}, "ingress-secret")
    assert not audio().authorized_ingress(
        {"Authorization": "Bearer wrong"},
        "ingress-secret",
    )


def test_setup_registers_audio_ingress_view():
    registered = []

    class Http:
        def register_view(self, view):
            registered.append(view)

    class Hass:
        http = Http()
        data = {}

    ingress = object()
    audio().register_audio_ingress_view(Hass(), ingress, "secret")

    assert len(registered) == 1
    assert registered[0].url == "/api/nyra/audio"
    assert registered[0].requires_auth is False
    assert registered[0].ingress is ingress


def test_audio_ingress_view_is_reused_on_reload_and_disabled_on_unload():
    registered = []

    class Http:
        def register_view(self, view):
            registered.append(view)

    class Hass:
        http = Http()
        data = {}

    hass = Hass()
    first = audio().register_audio_ingress_view(
        hass, "ingress-a", "token-a", owner_entry_id="entry-a"
    )
    second = audio().register_audio_ingress_view(
        hass, "ingress-b", "token-b", owner_entry_id="entry-a"
    )

    assert first is second
    assert len(registered) == 1
    assert second.ingress == "ingress-b"
    assert second.token == "token-b"

    audio().disable_audio_ingress_view(hass, second)
    assert second.ingress is None
    assert second.requires_auth is True
    assert second.owner_entry_id is None

    third = audio().register_audio_ingress_view(
        hass, "ingress-c", "token-c", owner_entry_id="entry-c"
    )
    assert third is second
    assert third.ingress == "ingress-c"


def test_audio_ingress_rejects_a_second_config_entry():
    class Http:
        def register_view(self, view):
            pass

    class Hass:
        http = Http()
        data = {}

    hass = Hass()
    audio().register_audio_ingress_view(
        hass, "ingress-a", "token-a", owner_entry_id="entry-a"
    )
    with pytest.raises(RuntimeError, match="already owned"):
        audio().register_audio_ingress_view(
            hass, "ingress-b", "token-b", owner_entry_id="entry-b"
        )


@pytest.mark.asyncio
async def test_runtime_unload_disables_registered_audio_ingress():
    import homeassistant.custom_components.nyra as nyra

    class View:
        ingress = object()

        def configure(self, ingress, token):
            self.ingress = ingress

    view = View()

    class Hass:
        data = {"nyra": {"audio_ingress_view": view}}

    class Runtime:
        audio_ingress_view = view
        audio_ingress = type("Ingress", (), {
            "async_shutdown": lambda self: asyncio.sleep(0)
        })()

    runtime = Runtime()
    await nyra.unregister_audio_ingress(Hass(), runtime)

    assert view.ingress is None
    assert runtime.audio_ingress_view is None


@pytest.mark.asyncio
async def test_ha_websocket_ingress_relays_start_chunks_and_end():
    start = identification_start()

    class RouterSession:
        def __init__(self):
            self.chunks = []
            self.closed = False

        async def async_chunk(self, payload):
            self.chunks.append(payload)

        async def async_end(self):
            return {
                "outcome": "NOT_RECOGNIZED",
                "identified_user_id": None,
                "best_score": None,
                "diagnostic_id": "diag-2",
                "reason_code": "NO_PROFILES",
            }

        async def async_close(self):
            self.closed = True

    router_session = RouterSession()

    class Client:
        opened = []

        async def async_open(self, metadata):
            self.opened.append(metadata)
            return router_session

    class Incoming:
        def __init__(self):
            self.frames = [
                {"type": "TEXT", "data": start.to_wire()},
                {"type": "BINARY", "data": b"one"},
                {"type": "BINARY", "data": b"two"},
                {
                    "type": "TEXT",
                    "data": {"type": "END", "audio_stream_id": "audio-a"},
                },
            ]
            self.sent = []
            self.closed = False

        async def receive(self):
            return self.frames.pop(0)

        async def send_json(self, value):
            self.sent.append(value)

        async def close(self):
            self.closed = True

    client = Client()
    incoming = Incoming()

    await audio().HomeAssistantAudioIngress(client, SessionManager()).async_handle(incoming)

    opened = client.opened[0]
    assert opened.source_id == "speaker-kitchen"
    assert not hasattr(opened, "identity")
    assert router_session.chunks == [b"one", b"two"]
    assert incoming.sent == [
        {"type": "STARTED", "audio_stream_id": "audio-a"},
        {"type": "CHUNK", "audio_stream_id": "audio-a"},
        {"type": "CHUNK", "audio_stream_id": "audio-a"},
        {
            "type": "RESULT",
            "audio_stream_id": "audio-a",
            "result": {
                "outcome": "NOT_RECOGNIZED",
                "identified_user_id": None,
                "best_score": None,
                "diagnostic_id": "diag-2",
                "reason_code": "NO_PROFILES",
            },
        },
    ]
    assert router_session.closed
    assert incoming.closed


@pytest.mark.asyncio
async def test_ha_websocket_disconnect_closes_router_stream():
    start = identification_start()

    class RouterSession:
        closed = False

        async def async_close(self):
            self.closed = True

    router_session = RouterSession()

    class Client:
        async def async_open(self, metadata):
            return router_session

    class Incoming:
        def __init__(self):
            self.frames = [
                {"type": "TEXT", "data": start.to_wire()},
                {"type": "CLOSE", "data": None},
            ]

        async def receive(self):
            return self.frames.pop(0)

        async def send_json(self, value):
            pass

        async def close(self):
            pass

    await audio().HomeAssistantAudioIngress(Client(), SessionManager()).async_handle(Incoming())

    assert router_session.closed


@pytest.mark.asyncio
async def test_ha_ingress_times_out_idle_device_and_closes_router_stream():
    start = identification_start()

    class RouterSession:
        closed = False

        async def async_close(self):
            self.closed = True

    router_session = RouterSession()

    class Client:
        async def async_open(self, metadata):
            return router_session

    class Incoming:
        def __init__(self):
            self.first = True
            self.sent = []
            self.closed = False

        async def receive(self):
            if self.first:
                self.first = False
                return {"type": "TEXT", "data": start.to_wire()}
            await asyncio.Event().wait()

        async def send_json(self, value):
            self.sent.append(value)

        async def close(self):
            self.closed = True

    incoming = Incoming()
    ingress = audio().HomeAssistantAudioIngress(Client(), SessionManager(), timeout_seconds=.01)
    await ingress.async_handle(incoming)

    assert incoming.sent[-1]["reason_code"] == "TIMEOUT"
    assert incoming.sent[-1]["audio_stream_id"] == "audio-a"
    assert router_session.closed
    assert incoming.closed


@pytest.mark.asyncio
async def test_ingress_capacity_and_shutdown_close_active_connections():
    start = identification_start()
    blocked = asyncio.Event()

    class RouterSession:
        closed = False

        async def async_close(self):
            self.closed = True

    router_session = RouterSession()

    class Client:
        async def async_open(self, metadata):
            return router_session

    class Incoming:
        def __init__(self, frames):
            self.frames = frames
            self.sent = []
            self.closed = False

        async def receive(self):
            if self.frames:
                return self.frames.pop(0)
            blocked.set()
            await asyncio.Event().wait()

        async def send_json(self, value):
            self.sent.append(value)

        async def close(self):
            self.closed = True

    ingress = audio().HomeAssistantAudioIngress(
        Client(), SessionManager(), timeout_seconds=10, max_active_streams=1
    )
    active = Incoming([{"type": "TEXT", "data": start.to_wire()}])
    active_task = asyncio.create_task(ingress.async_handle(active))
    await blocked.wait()

    rejected = Incoming([])
    await ingress.async_handle(rejected)
    assert rejected.sent[-1]["reason_code"] == "CAPACITY_EXCEEDED"

    await ingress.async_shutdown()
    await asyncio.gather(active_task, return_exceptions=True)
    assert router_session.closed
    assert active.closed


@pytest.mark.asyncio
async def test_device_disconnect_during_end_cancels_router_processing():
    start = identification_start()
    ending = asyncio.Event()
    cancelled = asyncio.Event()

    class RouterSession:
        closed = False

        async def async_end(self):
            ending.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def async_close(self):
            self.closed = True

    router_session = RouterSession()

    class Client:
        async def async_open(self, metadata):
            return router_session

    class Incoming:
        def __init__(self):
            self.frames = [
                {"type": "TEXT", "data": start.to_wire()},
                {"type": "TEXT", "data": {"type": "END", "audio_stream_id": "audio-a"}},
                {"type": "CLOSE", "data": None},
            ]

        async def receive(self):
            return self.frames.pop(0)

        async def send_json(self, value):
            pass

        async def close(self):
            pass

    await audio().HomeAssistantAudioIngress(
        Client(), SessionManager(), timeout_seconds=1
    ).async_handle(Incoming())

    assert ending.is_set()
    assert cancelled.is_set()
    assert router_session.closed


@pytest.mark.asyncio
async def test_ingress_timeout_during_end_cancels_router_processing():
    start = identification_start()
    cancelled = asyncio.Event()

    class RouterSession:
        closed = False

        async def async_end(self):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        async def async_close(self):
            self.closed = True

    router_session = RouterSession()

    class Client:
        async def async_open(self, metadata):
            return router_session

    class Incoming:
        def __init__(self):
            self.frames = [
                {"type": "TEXT", "data": start.to_wire()},
                {"type": "TEXT", "data": {"type": "END", "audio_stream_id": "audio-a"}},
            ]
            self.sent = []

        async def receive(self):
            if self.frames:
                return self.frames.pop(0)
            await asyncio.Event().wait()

        async def send_json(self, value):
            self.sent.append(value)

        async def close(self):
            pass

    incoming = Incoming()
    await audio().HomeAssistantAudioIngress(
        Client(), SessionManager(), timeout_seconds=.01
    ).async_handle(incoming)

    assert incoming.sent[-1]["reason_code"] == "TIMEOUT"
    assert cancelled.is_set()
    assert router_session.closed
