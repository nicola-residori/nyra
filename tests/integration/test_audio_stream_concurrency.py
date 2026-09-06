from __future__ import annotations

import asyncio
import importlib

import pytest


class IsolatedSink:
    def __init__(self):
        self.buffers = {}
        self.results = {}

    async def start(self, metadata):
        self.buffers[metadata.audio_stream_id] = bytearray()

    async def chunk(self, audio_stream_id, payload):
        self.buffers[audio_stream_id].extend(payload)

    async def end(self, audio_stream_id):
        payload = bytes(self.buffers[audio_stream_id])
        result = {"audio_stream_id": audio_stream_id, "payload": payload}
        self.results[audio_stream_id] = result
        return result

    async def abort(self, audio_stream_id, reason):
        self.buffers.pop(audio_stream_id, None)


def meta(stream_id, source_id):
    return {
        "audio_stream_id": stream_id,
        "purpose": "IDENTIFICATION",
        "session_id": f"session-{source_id}",
        "request_id": f"request-{source_id}",
        "source_id": source_id,
        "trace_id": f"trace-{source_id}",
        "span_id": f"span-{source_id}",
    }


@pytest.mark.asyncio
async def test_interleaved_streams_never_cross_bytes_or_results():
    m = importlib.import_module("router.audio_streaming")
    sink = IsolatedSink()
    registry = m.AudioStreamRegistry(sink=sink, timeout_seconds=1)

    await registry.start(meta("audio-a", "speaker-a"), connection_id="conn-a")
    await registry.start(meta("audio-b", "speaker-b"), connection_id="conn-b")

    await registry.chunk("audio-a", b"A1")
    await asyncio.sleep(0)
    await registry.chunk("audio-b", b"B1")
    await registry.chunk("audio-a", b"A2")
    await asyncio.sleep(0)
    await registry.chunk("audio-b", b"B2")

    result_a, result_b = await asyncio.gather(
        registry.end("audio-a"),
        registry.end("audio-b"),
    )

    assert sink.results["audio-a"]["payload"] == b"A1A2"
    assert sink.results["audio-b"]["payload"] == b"B1B2"
    assert result_a["audio_stream_id"] == "audio-a"
    assert result_b["audio_stream_id"] == "audio-b"
    assert registry.active_stream_ids() == ()
