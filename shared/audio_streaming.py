from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from collections import OrderedDict
import math
from enum import Enum
from typing import Any, Mapping, Protocol


TECHNICAL_REASONS = frozenset({
    'TIMEOUT', 'UNKNOWN_STREAM', 'CLOSED_STREAM', 'DUPLICATE_START',
    'INVALID_START', 'INVALID_MESSAGE', 'MESSAGE_TOO_LARGE', 'STREAM_TOO_LARGE',
    'CAPACITY_EXCEEDED', 'PROCESSING_CAPACITY_EXCEEDED', 'SPEAKER_ID_UNAVAILABLE',
    'INVALID_DOWNSTREAM_RESPONSE', 'STREAM_FAILED',
})


class AudioStreamPurpose(str, Enum):
    IDENTIFICATION = "IDENTIFICATION"
    ENROLLMENT = "ENROLLMENT"
    WAKE_WORD_CAPTURE = "WAKE_WORD_CAPTURE"


class AudioStreamError(RuntimeError):
    pass


class InvalidAudioStreamStart(AudioStreamError):
    pass


class UnknownAudioStream(AudioStreamError):
    pass


class DuplicateAudioStream(AudioStreamError):
    pass


class ClosedAudioStream(AudioStreamError):
    pass


@dataclass(frozen=True)
class AudioStreamStart:
    audio_stream_id: str
    purpose: AudioStreamPurpose
    session_id: str | None
    request_id: str | None
    source_id: str | None
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    language: str | None = None
    enrollment_session_id: str | None = None
    wake_word_session_id: str | None = None
    user_id: str | None = None
    wake_word_text: str | None = None
    audio_format: str = "wav"
    sample_rate: int = 16000
    channels: int = 1

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "AudioStreamStart":
        try:
            audio_stream_id = value["audio_stream_id"]
            purpose = AudioStreamPurpose(value["purpose"])
            trace_id = value["trace_id"]
            span_id = value["span_id"]
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidAudioStreamStart("invalid START metadata") from exc

        required_strings = {
            "audio_stream_id": audio_stream_id,
            "trace_id": trace_id,
            "span_id": span_id,
        }
        if any(not isinstance(item, str) or not item.strip() or len(item) > 1024 for item in required_strings.values()):
            raise InvalidAudioStreamStart("invalid START metadata")

        optional = {}
        for name in ("session_id", "request_id", "source_id", "parent_span_id", "language",
                     "enrollment_session_id", "wake_word_session_id", "user_id", "wake_word_text"):
            item = value.get(name)
            if item is not None and (not isinstance(item, str) or not item.strip() or len(item) > 1024):
                raise InvalidAudioStreamStart(f"invalid {name}")
            optional[name] = item

        if purpose is AudioStreamPurpose.IDENTIFICATION and not optional["request_id"]:
            raise InvalidAudioStreamStart("IDENTIFICATION requires request_id")
        required = {
            AudioStreamPurpose.ENROLLMENT: ("enrollment_session_id", "user_id"),
            AudioStreamPurpose.WAKE_WORD_CAPTURE: ("wake_word_session_id", "user_id", "wake_word_text", "language"),
        }.get(purpose, ())
        if any(not optional[name] for name in required):
            raise InvalidAudioStreamStart("missing operation correlation")
        audio_format = value.get("audio_format", "wav")
        sample_rate = value.get("sample_rate", 16000)
        channels = value.get("channels", 1)
        if audio_format not in ("wav", "pcm_s16le") or type(sample_rate) is not int or not 8000 <= sample_rate <= 96000 or type(channels) is not int or channels not in (1, 2):
            raise InvalidAudioStreamStart("invalid audio format")

        return cls(
            audio_stream_id=audio_stream_id,
            purpose=purpose,
            **optional,
            audio_format=audio_format, sample_rate=sample_rate, channels=channels,
            trace_id=trace_id,
            span_id=span_id,
        )


class AudioStreamSink(Protocol):
    async def start(self, metadata: AudioStreamStart) -> None: ...
    async def chunk(self, audio_stream_id: str, payload: bytes) -> None: ...
    async def end(self, audio_stream_id: str) -> Any: ...
    async def abort(self, audio_stream_id: str, reason: str) -> None: ...


@dataclass
class _ActiveStream:
    metadata: AudioStreamStart
    connection_id: str | None
    deadline: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    timeout_task: asyncio.Task | None = None
    byte_count: int = 0


class AudioStreamRegistry:
    def __init__(self, sink: AudioStreamSink, timeout_seconds: float,
                 max_active_streams: int = 32, max_stream_bytes: int = 8 * 1024 * 1024,
                 max_chunk_bytes: int = 256 * 1024, closed_capacity: int = 1024):
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        if min(max_active_streams, max_stream_bytes, max_chunk_bytes, closed_capacity) <= 0:
            raise ValueError("stream limits must be positive")
        self.sink = sink
        self.timeout_seconds = float(timeout_seconds)
        self.max_active_streams = max_active_streams
        self.max_stream_bytes = max_stream_bytes
        self.max_chunk_bytes = max_chunk_bytes
        self.closed_capacity = closed_capacity
        self._active: dict[str, _ActiveStream] = {}
        self._closed: OrderedDict[str, None] = OrderedDict()

    def active_stream_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._active))

    async def start(self, metadata: AudioStreamStart | Mapping[str, Any], connection_id: str | None = None) -> None:
        metadata = AudioStreamStart.from_mapping(asdict(metadata) if isinstance(metadata, AudioStreamStart) else metadata)
        stream_id = metadata.audio_stream_id
        if stream_id in self._active:
            raise DuplicateAudioStream(stream_id)
        if stream_id in self._closed:
            raise ClosedAudioStream(stream_id)
        if len(self._active) >= self.max_active_streams:
            raise AudioStreamError("CAPACITY_EXCEEDED")
        active = _ActiveStream(metadata, connection_id, asyncio.get_running_loop().time() + self.timeout_seconds)
        # Reserve before the first await; all registry access is on the app event loop.
        self._active[stream_id] = active
        active.timeout_task = asyncio.create_task(self._expire(stream_id, active))
        await self._call(stream_id, active, lambda: self.sink.start(metadata))

    async def chunk(self, audio_stream_id: str, payload: bytes) -> None:
        active = self._require_active(audio_stream_id)
        if not isinstance(payload, bytes):
            raise TypeError("audio payload must be bytes")
        if len(payload) > self.max_chunk_bytes or active.byte_count + len(payload) > self.max_stream_bytes:
            await self._abort(audio_stream_id, active, "STREAM_TOO_LARGE")
            raise AudioStreamError("STREAM_TOO_LARGE")
        active.byte_count += len(payload)
        await self._call(audio_stream_id, active, lambda: self.sink.chunk(audio_stream_id, payload))

    async def end(self, audio_stream_id: str) -> Any:
        active = self._require_active(audio_stream_id)
        result = await self._call(audio_stream_id, active, lambda: self.sink.end(audio_stream_id))
        self._finish(audio_stream_id, active)
        return result

    async def _call(self, stream_id, active, operation):
        try:
            async with asyncio.timeout_at(active.deadline):
                async with active.lock:
                    if self._active.get(stream_id) is not active:
                        raise ClosedAudioStream(stream_id)
                    return await operation()
        except BaseException:
            await self._abort(stream_id, active, "stream_failed")
            raise

    async def disconnect(self, connection_id: str) -> None:
        await asyncio.gather(*(self._abort(sid, active, "disconnect")
                               for sid, active in list(self._active.items())
                               if active.connection_id == connection_id))

    async def close(self) -> None:
        await asyncio.gather(*(self._abort(sid, active, "shutdown")
                               for sid, active in list(self._active.items())))

    async def _abort(self, stream_id, active, reason):
        if self._active.get(stream_id) is not active:
            return
        self._finish(stream_id, active)
        try:
            async with asyncio.timeout(min(self.timeout_seconds, 1)):
                await self.sink.abort(stream_id, reason)
        except Exception:
            pass  # Transport may already be gone; local state is always released.

    def _require_active(self, audio_stream_id: str) -> _ActiveStream:
        if audio_stream_id in self._active:
            return self._active[audio_stream_id]
        if audio_stream_id in self._closed:
            raise ClosedAudioStream(audio_stream_id)
        raise UnknownAudioStream(audio_stream_id)

    def _finish(self, audio_stream_id: str, active: _ActiveStream) -> None:
        if self._active.get(audio_stream_id) is not active:
            return
        self._active.pop(audio_stream_id)
        self._closed[audio_stream_id] = None
        while len(self._closed) > self.closed_capacity:
            self._closed.popitem(last=False)
        if active.timeout_task is not None and active.timeout_task is not asyncio.current_task():
            active.timeout_task.cancel()

    async def _expire(self, stream_id, active):
        try:
            await asyncio.sleep(max(0, active.deadline - asyncio.get_running_loop().time()))
            await self._abort(stream_id, active, "timeout")
        except asyncio.CancelledError:
            pass
