from __future__ import annotations

import asyncio
import importlib

import pytest


def streaming():
    return importlib.import_module("router.audio_streaming")


class RecordingSink:
    def __init__(self):
        self.started = []
        self.chunks = []
        self.ended = []
        self.aborted = []

    async def start(self, metadata):
        self.started.append(metadata)

    async def chunk(self, audio_stream_id, payload):
        self.chunks.append((audio_stream_id, payload))

    async def end(self, audio_stream_id):
        self.ended.append(audio_stream_id)
        return {"audio_stream_id": audio_stream_id, "status": "completed"}

    async def abort(self, audio_stream_id, reason):
        self.aborted.append((audio_stream_id, reason))


def metadata(stream_id="audio-a", purpose="IDENTIFICATION"):
    return {
        "audio_stream_id": stream_id,
        "purpose": purpose,
        "session_id": "ses-1",
        "request_id": "req-1",
        "source_id": "speaker-a",
        "trace_id": "trace-1",
        "span_id": "span-1",
    }


@pytest.mark.asyncio
async def test_stream_lifecycle_relays_start_binary_chunks_and_end():
    m = streaming()
    sink = RecordingSink()
    registry = m.AudioStreamRegistry(sink=sink, timeout_seconds=1)

    await registry.start(metadata())
    await registry.chunk("audio-a", b"abc")
    await registry.chunk("audio-a", b"def")
    result = await registry.end("audio-a")

    assert sink.started[0].audio_stream_id == "audio-a"
    assert sink.started[0].purpose is m.AudioStreamPurpose.IDENTIFICATION
    assert sink.chunks == [("audio-a", b"abc"), ("audio-a", b"def")]
    assert sink.ended == ["audio-a"]
    assert result == {"audio_stream_id": "audio-a", "status": "completed"}
    assert registry.active_stream_ids() == ()


@pytest.mark.asyncio
async def test_unknown_stream_chunk_and_end_are_rejected():
    m = streaming()
    registry = m.AudioStreamRegistry(sink=RecordingSink(), timeout_seconds=1)

    with pytest.raises(m.UnknownAudioStream):
        await registry.chunk("missing", b"x")
    with pytest.raises(m.UnknownAudioStream):
        await registry.end("missing")


@pytest.mark.asyncio
async def test_duplicate_start_is_rejected_while_stream_is_active():
    m = streaming()
    registry = m.AudioStreamRegistry(sink=RecordingSink(), timeout_seconds=1)

    await registry.start(metadata())
    with pytest.raises(m.DuplicateAudioStream):
        await registry.start(metadata())


@pytest.mark.asyncio
async def test_chunk_after_close_and_duplicate_end_are_rejected():
    m = streaming()
    registry = m.AudioStreamRegistry(sink=RecordingSink(), timeout_seconds=1)

    await registry.start(metadata())
    await registry.end("audio-a")

    with pytest.raises(m.ClosedAudioStream):
        await registry.chunk("audio-a", b"x")
    with pytest.raises(m.ClosedAudioStream):
        await registry.end("audio-a")


@pytest.mark.asyncio
async def test_disconnect_aborts_and_cleans_only_connection_streams():
    m = streaming()
    sink = RecordingSink()
    registry = m.AudioStreamRegistry(sink=sink, timeout_seconds=1)

    await registry.start(metadata("audio-a"), connection_id="conn-a")
    await registry.start(metadata("audio-b"), connection_id="conn-b")

    await registry.disconnect("conn-a")

    assert ("audio-a", "disconnect") in sink.aborted
    assert registry.active_stream_ids() == ("audio-b",)


@pytest.mark.asyncio
async def test_timeout_aborts_start_without_end_and_cleans_state():
    m = streaming()
    sink = RecordingSink()
    registry = m.AudioStreamRegistry(sink=sink, timeout_seconds=.01)

    await registry.start(metadata())
    await asyncio.sleep(.03)

    assert ("audio-a", "timeout") in sink.aborted
    assert registry.active_stream_ids() == ()


@pytest.mark.parametrize("purpose", ["IDENTIFICATION", "ENROLLMENT", "WAKE_WORD_CAPTURE"])
def test_supported_purposes_are_typed(purpose):
    m = streaming()
    parsed = m.AudioStreamStart.from_mapping({**metadata(purpose=purpose),
        "enrollment_session_id": "enr-1", "wake_word_session_id": "ww-1",
        "user_id": "u1", "wake_word_text": "Hello", "language": "en"})
    assert parsed.purpose.value == purpose


def test_unknown_purpose_is_rejected():
    m = streaming()
    with pytest.raises(m.InvalidAudioStreamStart):
        m.AudioStreamStart.from_mapping(metadata(purpose="STT"))


from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from router.app import create_app
from router.config import RouterSettings


def ws_app(tmp_path, *, token=None, timeout=1):
    app = create_app(RouterSettings(database_path=tmp_path / 'router.db', ingress_token=token))
    sink = RecordingSink()
    app.state.audio_streams = streaming().AudioStreamRegistry(sink=sink, timeout_seconds=timeout)
    return app, sink


def test_websocket_relays_bytes_and_correlated_result(tmp_path):
    app, sink = ws_app(tmp_path)
    with TestClient(app) as client, client.websocket_connect('/v1/audio/stream') as ws:
        ws.send_json({'type': 'START', **metadata()})
        assert ws.receive_json() == {'type': 'STARTED', 'audio_stream_id': 'audio-a'}
        ws.send_bytes(b'abc')
        assert ws.receive_json()['type'] == 'CHUNK'
        ws.send_json({'type': 'END', 'audio_stream_id': 'audio-a'})
        result = ws.receive_json()
        assert result == {'type': 'RESULT', 'audio_stream_id': 'audio-a', 'result': {'audio_stream_id': 'audio-a', 'status': 'completed'}}
    assert sink.chunks == [('audio-a', b'abc')]
    assert app.state.audio_streams.active_stream_ids() == ()


def test_websocket_auth_matches_router_ingress(tmp_path):
    app, sink = ws_app(tmp_path, token='test-secret')
    with TestClient(app) as client:
        for headers in ({}, {'authorization': 'Bearer wrong'}):
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect('/v1/audio/stream', headers=headers):
                    pass
            assert exc.value.code == 4401
        with client.websocket_connect('/v1/audio/stream', headers={'authorization': 'Bearer test-secret'}) as ws:
            ws.send_json({'type': 'START', **metadata()})
            assert ws.receive_json()['type'] == 'STARTED'
    assert app.state.audio_streams.active_stream_ids() == ()


@pytest.mark.parametrize('frame,code', [
    ({'type': 'END', 'audio_stream_id': 'missing'}, 'UNKNOWN_STREAM'),
    ([], 'INVALID_MESSAGE'),
    ({'type': 'NOPE'}, 'INVALID_MESSAGE'),
])
def test_websocket_rejects_invalid_sequence(tmp_path, frame, code):
    app, _ = ws_app(tmp_path)
    with TestClient(app) as client, client.websocket_connect('/v1/audio/stream') as ws:
        ws.send_json(frame)
        result = ws.receive_json()
        assert result['type'] == 'ERROR'
        assert result['outcome'] == 'FAILED'
        assert result['reason_code'] == code
    assert app.state.audio_streams.active_stream_ids() == ()


def test_websocket_disconnect_aborts(tmp_path):
    app, sink = ws_app(tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect('/v1/audio/stream') as ws:
            ws.send_json({'type': 'START', **metadata()})
            ws.receive_json()
            ws.send_bytes(b'partial')
            ws.receive_json()
    assert sink.aborted == [('audio-a', 'disconnect')]
    assert app.state.audio_streams.active_stream_ids() == ()


def test_websocket_timeout_emits_failure_and_cleans(tmp_path):
    app, sink = ws_app(tmp_path, timeout=.03)
    with TestClient(app) as client, client.websocket_connect('/v1/audio/stream') as ws:
        ws.send_json({'type': 'START', **metadata()})
        assert ws.receive_json()['type'] == 'STARTED'
        result = ws.receive_json()
        assert result['outcome'] == 'FAILED'
        assert result['reason_code'] == 'TIMEOUT'
    assert app.state.audio_streams.active_stream_ids() == ()


def test_websocket_cannot_end_another_connections_stream(tmp_path):
    app, sink = ws_app(tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect('/v1/audio/stream') as a, client.websocket_connect('/v1/audio/stream') as b:
            a.send_json({'type': 'START', **metadata('a')})
            a.receive_json()
            b.send_json({'type': 'END', 'audio_stream_id': 'a'})
            assert b.receive_json()['reason_code'] == 'UNKNOWN_STREAM'
            a.send_bytes(b'A')
            assert a.receive_json()['type'] == 'CHUNK'
            a.send_json({'type': 'END', 'audio_stream_id': 'a'})
            assert a.receive_json()['type'] == 'RESULT'
    assert sink.chunks == [('a', b'A')]


@pytest.mark.parametrize('after', ['END', 'CHUNK'])
def test_websocket_rejects_frames_after_end(tmp_path, after):
    app, _ = ws_app(tmp_path)
    with TestClient(app) as client, client.websocket_connect('/v1/audio/stream') as ws:
        ws.send_json({'type': 'START', **metadata()})
        ws.receive_json()
        ws.send_json({'type': 'END', 'audio_stream_id': 'audio-a'})
        ws.receive_json()
        if after == 'END':
            ws.send_json({'type': 'END', 'audio_stream_id': 'audio-a'})
        else:
            ws.send_bytes(b'late')
        assert ws.receive_json()['reason_code'] == 'CLOSED_STREAM'


@pytest.mark.parametrize('purpose,fields', [
    ('ENROLLMENT', {'enrollment_session_id': 'enr-1', 'user_id': 'u1'}),
    ('WAKE_WORD_CAPTURE', {'wake_word_session_id': 'ww-1', 'user_id': 'u1', 'wake_word_text': 'Hello', 'language': 'en'}),
])
def test_start_preserves_typed_operation_correlation(purpose, fields):
    value = {**metadata(purpose=purpose), **fields, 'parent_span_id': 'parent', 'language': 'en'}
    value.pop('session_id')
    parsed = streaming().AudioStreamStart.from_mapping(value)
    for key, item in fields.items():
        assert getattr(parsed, key) == item
    assert parsed.parent_span_id == 'parent'


@pytest.mark.parametrize('purpose', ['ENROLLMENT', 'WAKE_WORD_CAPTURE'])
def test_conversation_session_is_not_an_operation_id(purpose):
    with pytest.raises(streaming().InvalidAudioStreamStart):
        streaming().AudioStreamStart.from_mapping(metadata(purpose=purpose))


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['start', 'chunk', 'end', 'abort'])
async def test_sink_failure_always_releases_registry(failure):
    class FailingSink(RecordingSink):
        async def start(self, metadata):
            if failure == 'start':
                raise RuntimeError('downstream unavailable')
            await super().start(metadata)
        async def chunk(self, stream_id, payload):
            if failure == 'chunk':
                raise RuntimeError('downstream unavailable')
        async def end(self, stream_id):
            if failure == 'end':
                raise RuntimeError('downstream unavailable')
        async def abort(self, stream_id, reason):
            raise RuntimeError('already disconnected')
    registry = streaming().AudioStreamRegistry(FailingSink(), .1)
    try:
        await registry.start(metadata(), connection_id='a')
        if failure == 'chunk':
            await registry.chunk('audio-a', b'a')
        elif failure == 'end':
            await registry.end('audio-a')
        else:
            await registry.disconnect('a')
    except RuntimeError:
        pass
    assert registry.active_stream_ids() == ()


@pytest.mark.asyncio
async def test_stalled_sink_does_not_block_other_stream_or_timeout():
    entered = asyncio.Event()
    class StalledSink(RecordingSink):
        async def chunk(self, stream_id, payload):
            if stream_id == 'a':
                entered.set()
                await asyncio.Event().wait()
            await super().chunk(stream_id, payload)
    registry = streaming().AudioStreamRegistry(StalledSink(), .1)
    await registry.start(metadata('a'))
    await registry.start(metadata('b'))
    task = asyncio.create_task(registry.chunk('a', b'a'))
    await entered.wait()
    try:
        result = await asyncio.wait_for(registry.end('b'), .05)
        assert result['audio_stream_id'] == 'b'
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    await asyncio.sleep(.12)
    assert registry.active_stream_ids() == ()


@pytest.mark.parametrize('timeout', [float('nan'), float('inf')])
def test_registry_rejects_nonfinite_timeout(timeout):
    with pytest.raises(ValueError):
        streaming().AudioStreamRegistry(RecordingSink(), timeout)


@pytest.mark.asyncio
async def test_registry_capacity_and_audio_bounds_cleanup():
    registry = streaming().AudioStreamRegistry(RecordingSink(), 1, max_active_streams=1,
                                               max_stream_bytes=3, max_chunk_bytes=2, closed_capacity=2)
    await registry.start(metadata('a'))
    with pytest.raises(streaming().AudioStreamError, match='CAPACITY_EXCEEDED'):
        await registry.start(metadata('b'))
    await registry.chunk('a', b'12')
    with pytest.raises(streaming().AudioStreamError, match='STREAM_TOO_LARGE'):
        await registry.chunk('a', b'34')
    assert registry.active_stream_ids() == ()
    await registry.start(metadata('b'))
    with pytest.raises(streaming().AudioStreamError, match='STREAM_TOO_LARGE'):
        await registry.chunk('b', b'123')
    await registry.start(metadata('c'))
    await registry.end('c')
    # Evicted tombstones do not accumulate forever; stale chunks remain unknown.
    with pytest.raises(streaming().UnknownAudioStream):
        await registry.chunk('a', b'1')


def test_websocket_duplicate_start_does_not_damage_other_owner(tmp_path):
    app, sink = ws_app(tmp_path)
    with TestClient(app) as client:
        with client.websocket_connect('/v1/audio/stream') as a, client.websocket_connect('/v1/audio/stream') as b:
            a.send_json({'type': 'START', **metadata()}); a.receive_json()
            b.send_json({'type': 'START', **metadata()})
            assert b.receive_json()['reason_code'] == 'DUPLICATE_START'
            a.send_bytes(b'ok'); assert a.receive_json()['type'] == 'CHUNK'
            a.send_json({'type': 'END', 'audio_stream_id': 'audio-a'})
            assert a.receive_json()['type'] == 'RESULT'
    assert sink.aborted == []


@pytest.mark.parametrize('frame', ['{', '"text"'])
def test_malformed_json_aborts_owned_stream(tmp_path, frame):
    app, sink = ws_app(tmp_path)
    with TestClient(app) as client, client.websocket_connect('/v1/audio/stream') as ws:
        ws.send_json({'type': 'START', **metadata()}); ws.receive_json()
        ws.send_text(frame)
        assert ws.receive_json()['reason_code'] == 'INVALID_MESSAGE'
    assert app.state.audio_streams.active_stream_ids() == ()


def test_metadata_frame_is_bounded(tmp_path):
    app, _ = ws_app(tmp_path)
    with TestClient(app) as client, client.websocket_connect('/v1/audio/stream') as ws:
        ws.send_json({'type': 'START', **metadata(), 'ignored': 'x' * 20000})
        assert ws.receive_json()['reason_code'] == 'MESSAGE_TOO_LARGE'
    assert app.state.audio_streams.active_stream_ids() == ()


@pytest.mark.asyncio
async def test_wire_disconnect_cancels_inflight_end_without_waiting_for_timeout():
    from fastapi import WebSocket
    from shared.audio_websocket import serve_audio
    import json
    queue = asyncio.Queue()
    replies = asyncio.Queue()
    ending = asyncio.Event()
    cancelled = asyncio.Event()
    class SlowSink(RecordingSink):
        async def end(self, stream_id):
            ending.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
    registry = streaming().AudioStreamRegistry(SlowSink(), 10)
    ws = WebSocket({'type': 'websocket'}, queue.get, replies.put)
    await queue.put({'type': 'websocket.connect'})
    task = asyncio.create_task(serve_audio(ws, registry))
    assert (await replies.get())['type'] == 'websocket.accept'
    await queue.put({'type': 'websocket.receive', 'text': json.dumps({'type': 'START', **metadata()})})
    await replies.get()
    await queue.put({'type': 'websocket.receive', 'text': json.dumps({'type': 'END', 'audio_stream_id': 'audio-a'})})
    await ending.wait()
    await queue.put({'type': 'websocket.disconnect', 'code': 1000})
    done, _ = await asyncio.wait({task}, timeout=.1)
    try:
        assert task in done, 'disconnect must interrupt END processing'
        assert cancelled.is_set()
        assert registry.active_stream_ids() == ()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_completed_stream_idle_timeout_does_not_emit_failed_result(tmp_path):
    app, _ = ws_app(tmp_path, timeout=.05)
    with TestClient(app) as client, client.websocket_connect('/v1/audio/stream') as ws:
        ws.send_json({'type': 'START', **metadata()}); ws.receive_json()
        ws.send_json({'type': 'END', 'audio_stream_id': 'audio-a'})
        assert ws.receive_json()['type'] == 'RESULT'
        frame = ws.receive()
        assert frame['type'] == 'websocket.close'
        assert frame['code'] == 1000


@pytest.mark.parametrize('reason', ['TIMEOUT', 'CLOSED_STREAM', 'PROCESSING_CAPACITY_EXCEEDED'])
def test_downstream_reason_survives_websocket_error_envelope(tmp_path, reason):
    app, sink = ws_app(tmp_path)
    async def failed_start(metadata):
        raise streaming().AudioStreamError(reason)
    sink.start = failed_start
    with TestClient(app) as client, client.websocket_connect('/v1/audio/stream') as ws:
        ws.send_json({'type': 'START', **metadata()})
        assert ws.receive_json()['reason_code'] == reason
