from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import pytest

from fastapi.testclient import TestClient

from router.app import create_app
from router.config import RouterSettings


def speaker_app(tmp_path):
    path = Path(__file__).parents[2] / 'speaker-id' / 'app.py'
    spec = importlib.util.spec_from_file_location('speaker_audio_endpoint_test', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.create_app(tmp_path)


def start(stream_id):
    return {'type': 'START', 'audio_stream_id': stream_id, 'purpose': 'IDENTIFICATION',
            'request_id': 'req-' + stream_id, 'session_id': 'ses-' + stream_id,
            'source_id': 'same-speaker', 'trace_id': 'trace-' + stream_id, 'span_id': 'span-' + stream_id}


def test_speaker_endpoint_returns_typed_failure_for_malformed_audio(tmp_path):
    app = speaker_app(tmp_path)
    with TestClient(app) as client, client.websocket_connect('/v1/audio/stream') as ws:
        ws.send_json(start('a'))
        assert ws.receive_json()['type'] == 'STARTED'
        ws.send_bytes(b'invalid audio')
        assert ws.receive_json()['type'] == 'CHUNK'
        ws.send_json({'type': 'END', 'audio_stream_id': 'a'})
        result = ws.receive_json()
        assert result['audio_stream_id'] == 'a'
        assert result['result']['outcome'] == 'FAILED'
    assert app.state.audio_streams.active_stream_ids() == ()
    assert not list(tmp_path.rglob('*.wav'))


class ASGIConnection:
    """Adapt real TestClient WebSocket I/O to the production client's async port."""
    def __init__(self, client):
        self.context = client.websocket_connect('/v1/audio/stream')
        self.ws = self.context.__enter__()
    async def send(self, payload):
        await asyncio.to_thread(self.ws.send_bytes if isinstance(payload, bytes) else self.ws.send_text, payload)
    async def recv(self):
        return json.dumps(await asyncio.to_thread(self.ws.receive_json))
    async def close(self):
        await asyncio.to_thread(self.context.__exit__, None, None, None)


def test_router_forwards_to_real_speaker_endpoint_with_interleaved_streams(tmp_path):
    from router.audio_streaming import SpeakerAudioRelay
    app = speaker_app(tmp_path / 'speaker')
    with TestClient(app) as speaker:
        async def connect(url, **kwargs):
            return await asyncio.to_thread(ASGIConnection, speaker)
        router = create_app(RouterSettings(database_path=tmp_path / 'router.db'),
                            audio_sink=SpeakerAudioRelay('ws://speaker/v1/audio/stream', connect=connect))
        with TestClient(router) as client:
            with client.websocket_connect('/v1/audio/stream') as a, client.websocket_connect('/v1/audio/stream') as b:
                a.send_json(start('a')); assert a.receive_json()['audio_stream_id'] == 'a'
                b.send_json(start('b')); assert b.receive_json()['audio_stream_id'] == 'b'
                a.send_bytes(b'A1'); a.receive_json()
                b.send_bytes(b'B1'); b.receive_json()
                a.send_bytes(b'A2'); a.receive_json()
                b.send_bytes(b'B2'); b.receive_json()
                b.send_json({'type': 'END', 'audio_stream_id': 'b'})
                rb = b.receive_json()
                a.send_json({'type': 'END', 'audio_stream_id': 'a'})
                ra = a.receive_json()
                assert ra['audio_stream_id'] == 'a'
                assert rb['audio_stream_id'] == 'b'
                assert ra['result']['outcome'] == rb['result']['outcome'] == 'FAILED'
                assert ra['result']['diagnostic_id'] != rb['result']['diagnostic_id']
        assert router.state.audio_streams.active_stream_ids() == ()
    assert app.state.audio_streams.active_stream_ids() == ()


def test_router_default_relay_reports_unconfigured_service(tmp_path):
    app = create_app(RouterSettings(database_path=tmp_path / 'router.db'))
    with TestClient(app) as client, client.websocket_connect('/v1/audio/stream') as ws:
        ws.send_json(start('a'))
        result = ws.receive_json()
        assert result['outcome'] == 'FAILED'
    assert app.state.audio_streams.active_stream_ids() == ()


def test_speaker_interleaved_audio_produces_separate_processed_recordings(tmp_path):
    import io
    import wave
    app = speaker_app(tmp_path)
    def pcm(a, b):
        return (a.to_bytes(2, 'little', signed=True) + b.to_bytes(2, 'little', signed=True)) * 4000
    with TestClient(app) as client:
        with client.websocket_connect('/v1/audio/stream') as a, client.websocket_connect('/v1/audio/stream') as b:
            for ws, sid in ((a, 'a'), (b, 'b')):
                ws.send_json({**start(sid), 'audio_format': 'pcm_s16le'})
                assert ws.receive_json()['type'] == 'STARTED'
            a.send_bytes(pcm(8000, -8000)); a.receive_json()
            b.send_bytes(pcm(4000, 8000)); b.receive_json()
            a.send_json({'type': 'END', 'audio_stream_id': 'a'})
            ra = a.receive_json()['result']
            b.send_json({'type': 'END', 'audio_stream_id': 'b'})
            rb = b.receive_json()['result']
            assert ra['outcome'] == rb['outcome'] == 'NOT_RECOGNIZED'
    import sqlite3
    with sqlite3.connect(tmp_path / 'speaker_id.sqlite3') as db:
        paths = dict(db.execute('SELECT diagnostic_id, diagnostic_wav_path FROM identification_diagnostics'))
    with wave.open(str(paths[ra['diagnostic_id']]), 'rb') as wav:
        audio_a = wav.readframes(wav.getnframes())
    with wave.open(str(paths[rb['diagnostic_id']]), 'rb') as wav:
        audio_b = wav.readframes(wav.getnframes())
    assert int.from_bytes(audio_a[2:4], 'little', signed=True) < 0
    assert int.from_bytes(audio_b[2:4], 'little', signed=True) > 0
    assert app.state.audio_streams.active_stream_ids() == ()


@pytest.mark.asyncio
async def test_relay_rejects_wrong_correlation_and_closes_connection():
    from router.audio_streaming import SpeakerAudioRelay
    from shared.audio_streaming import AudioStreamRegistry, AudioStreamError
    class WrongCorrelation:
        closed = False
        async def send(self, data): pass
        async def recv(self): return json.dumps({'type': 'STARTED', 'audio_stream_id': 'another'})
        async def close(self): self.closed = True
    connection = WrongCorrelation()
    async def connect(*args, **kwargs): return connection
    registry = AudioStreamRegistry(SpeakerAudioRelay('ws://speaker', connect=connect), 1)
    with pytest.raises(AudioStreamError):
        await registry.start(start('a'))
    assert connection.closed
    assert registry.active_stream_ids() == ()


@pytest.mark.asyncio
@pytest.mark.parametrize('result', [[], {'outcome': 'GUEST'},
    {'outcome': 'NOT_RECOGNIZED', 'audio_stream_id': 'another'},
    {'outcome': 'NOT_RECOGNIZED', 'request_id': 'another'}])
async def test_relay_rejects_malformed_or_cross_correlated_result(result):
    from router.audio_streaming import SpeakerAudioRelay
    from shared.audio_streaming import AudioStreamRegistry, AudioStreamError
    class Connection:
        count = 0
        async def send(self, data): pass
        async def recv(self):
            self.count += 1
            return json.dumps({'type': 'STARTED' if self.count == 1 else 'RESULT',
                               'audio_stream_id': 'a', 'result': result})
        async def close(self): pass
    async def connect(*args, **kwargs): return Connection()
    registry = AudioStreamRegistry(SpeakerAudioRelay('ws://speaker', connect=connect), 1)
    await registry.start(start('a'))
    with pytest.raises(AudioStreamError):
        await registry.end('a')
    assert registry.active_stream_ids() == ()


@pytest.mark.asyncio
async def test_relay_preserves_correlated_downstream_technical_failure():
    from router.audio_streaming import SpeakerAudioRelay
    from shared.audio_streaming import AudioStreamRegistry, AudioStreamError
    class Connection:
        async def send(self, data): pass
        async def recv(self):
            return json.dumps({'type': 'ERROR', 'audio_stream_id': 'a', 'outcome': 'FAILED', 'reason_code': 'CAPACITY_EXCEEDED'})
        async def close(self): pass
    async def connect(*args, **kwargs): return Connection()
    registry = AudioStreamRegistry(SpeakerAudioRelay('ws://speaker', connect=connect), 1)
    with pytest.raises(AudioStreamError, match='CAPACITY_EXCEEDED'):
        await registry.start(start('a'))


def test_failed_start_keeps_attempted_stream_correlation(tmp_path):
    app = create_app(RouterSettings(database_path=tmp_path / 'router.db'))
    with TestClient(app) as client, client.websocket_connect('/v1/audio/stream') as ws:
        ws.send_json(start('a'))
        assert ws.receive_json()['audio_stream_id'] == 'a'
