"""Router relay registry (transport primitives shared with Speaker-ID)."""
from shared.audio_streaming import (
    TECHNICAL_REASONS, AudioStreamPurpose, AudioStreamError, InvalidAudioStreamStart,
    UnknownAudioStream, DuplicateAudioStream, ClosedAudioStream,
    AudioStreamStart, AudioStreamSink, AudioStreamRegistry,
)

import asyncio
from collections import OrderedDict
import json
from dataclasses import asdict

from router.speaker_identity import InvalidSpeakerIdentityResponse, _parse_realtime


class CorrelatedIdentityAudioSink:
    """Relay audio while making identification results awaitable by request ID."""

    def __init__(self, sink, *, wait_timeout_seconds: float = 30.0, result_capacity: int = 128):
        self.sink = sink
        self.wait_timeout_seconds = wait_timeout_seconds
        self.result_capacity = result_capacity
        self._metadata = {}
        self._waiting = {}
        self._results = OrderedDict()

    async def start(self, metadata):
        self._metadata[metadata.audio_stream_id] = metadata
        try:
            await self.sink.start(metadata)
        except BaseException:
            self._metadata.pop(metadata.audio_stream_id, None)
            raise

    async def chunk(self, audio_stream_id, payload):
        await self.sink.chunk(audio_stream_id, payload)

    async def end(self, audio_stream_id):
        metadata = self._metadata.pop(audio_stream_id, None)
        result = await self.sink.end(audio_stream_id)
        if (
            metadata is not None
            and metadata.purpose is AudioStreamPurpose.IDENTIFICATION
            and metadata.request_id
        ):
            try:
                parsed = _parse_realtime(result)
            except InvalidSpeakerIdentityResponse:
                pass
            else:
                self._publish(metadata.request_id, parsed)
        return result

    async def abort(self, audio_stream_id, reason):
        self._metadata.pop(audio_stream_id, None)
        await self.sink.abort(audio_stream_id, reason)

    async def identify(self, request, trace_id):
        request_id = getattr(request, "request_id", None)
        if request_id is None:
            return None
        key = str(request_id)
        cached = self._results.pop(key, None)
        if cached is not None:
            return cached
        future = self._waiting.get(key)
        if future is None:
            future = asyncio.get_running_loop().create_future()
            self._waiting[key] = future
        try:
            return await asyncio.wait_for(
                asyncio.shield(future), timeout=self.wait_timeout_seconds
            )
        except TimeoutError:
            return None
        finally:
            if self._waiting.get(key) is future:
                self._waiting.pop(key, None)

    def _publish(self, request_id, result):
        key = str(request_id)
        future = self._waiting.pop(key, None)
        if future is not None and not future.done():
            future.set_result(result)
            return
        self._results[key] = result
        self._results.move_to_end(key)
        while len(self._results) > self.result_capacity:
            self._results.popitem(last=False)


class SpeakerAudioRelay:
    """Backpressured socket-to-socket relay; retains no audio buffers."""
    def __init__(self, url: str | None, *, connect=None):
        self.url = url
        self.connect = connect
        self._connections = {}
        self._metadata = {}

    async def start(self, metadata):
        if not self.url:
            raise AudioStreamError('SPEAKER_ID_UNAVAILABLE')
        connect = self.connect
        if connect is None:
            from websockets.asyncio.client import connect
        ws = await connect(self.url, open_timeout=5, close_timeout=1, max_size=65536, max_queue=1)
        self._connections[metadata.audio_stream_id] = ws
        self._metadata[metadata.audio_stream_id] = metadata
        try:
            await ws.send(json.dumps({'type': 'START', **asdict(metadata)}))
            await self._receive(metadata.audio_stream_id, 'STARTED')
        except BaseException:
            await self.abort(metadata.audio_stream_id, 'start_failed')
            raise

    async def chunk(self, audio_stream_id, payload):
        await self._connections[audio_stream_id].send(payload)
        await self._receive(audio_stream_id, 'CHUNK')

    async def end(self, audio_stream_id):
        try:
            await self._connections[audio_stream_id].send(json.dumps({'type': 'END', 'audio_stream_id': audio_stream_id}))
            response = await self._receive(audio_stream_id, 'RESULT')
            return self._validated_result(audio_stream_id, response.get('result'))
        finally:
            await self.abort(audio_stream_id, 'completed')

    async def _receive(self, audio_stream_id, expected):
        response = json.loads(await self._connections[audio_stream_id].recv())
        if not isinstance(response, dict) or response.get('audio_stream_id') != audio_stream_id:
            raise AudioStreamError('INVALID_DOWNSTREAM_RESPONSE')
        if response.get('type') == 'ERROR' and response.get('outcome') == 'FAILED':
            reason = response.get('reason_code')
            if reason in TECHNICAL_REASONS:
                raise AudioStreamError(reason)
        if response.get('type') != expected:
            raise AudioStreamError('INVALID_DOWNSTREAM_RESPONSE')
        return response

    async def abort(self, audio_stream_id, reason):
        self._metadata.pop(audio_stream_id, None)
        ws = self._connections.pop(audio_stream_id, None)
        if ws is not None:
            await ws.close()


    def _validated_result(self, stream_id, result):
        metadata = self._metadata[stream_id]
        if not isinstance(result, dict):
            raise AudioStreamError('INVALID_DOWNSTREAM_RESPONSE')
        for key in ('audio_stream_id', 'request_id', 'session_id', 'source_id',
                    'enrollment_session_id', 'wake_word_session_id', 'trace_id'):
            if key in result and result[key] != getattr(metadata, key):
                raise AudioStreamError('INVALID_DOWNSTREAM_RESPONSE')
        if metadata.purpose is AudioStreamPurpose.IDENTIFICATION:
            from router.speaker_identity import _parse_realtime, InvalidSpeakerIdentityResponse
            try:
                parsed = _parse_realtime(result)
            except InvalidSpeakerIdentityResponse as exc:
                raise AudioStreamError('INVALID_DOWNSTREAM_RESPONSE') from exc
            return asdict(parsed)
        if result.get('status') not in {'ACCEPTED', 'REJECTED', 'FAILED'}:
            raise AudioStreamError('INVALID_DOWNSTREAM_RESPONSE')
        if metadata.purpose is AudioStreamPurpose.ENROLLMENT and result.get('user_id') != metadata.user_id:
            raise AudioStreamError('INVALID_DOWNSTREAM_RESPONSE')
        if metadata.purpose is AudioStreamPurpose.WAKE_WORD_CAPTURE and result.get('capture_id') != metadata.wake_word_session_id:
            raise AudioStreamError('INVALID_DOWNSTREAM_RESPONSE')
        return result
