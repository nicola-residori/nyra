"""One recording per WebSocket; binary frames belong exclusively to its owner."""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

from shared.audio_streaming import (
    TECHNICAL_REASONS, AudioStreamError, AudioStreamStart, ClosedAudioStream,
    DuplicateAudioStream, InvalidAudioStreamStart, UnknownAudioStream,
)


async def serve_audio(websocket: WebSocket, registry) -> None:
    await websocket.accept()
    connection_id = uuid4().hex
    stream_id = None
    attempted_id = None
    closed = False
    deadline = asyncio.get_running_loop().time() + registry.timeout_seconds
    try:
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            async with asyncio.timeout(max(0, remaining)):
                frame = await websocket.receive()
                if frame['type'] == 'websocket.disconnect':
                    raise WebSocketDisconnect(frame.get('code', 1000))
                if frame.get('bytes') is not None:
                    if closed:
                        raise ClosedAudioStream(stream_id)
                    if stream_id is None:
                        raise UnknownAudioStream('no START')
                    await registry.chunk(stream_id, frame['bytes'])
                    await websocket.send_json({'type': 'CHUNK', 'audio_stream_id': stream_id})
                    continue
                if len(frame.get('text') or '') > 16384:
                    raise AudioStreamError('MESSAGE_TOO_LARGE')
                message = json.loads(frame.get('text') or '')
                if not isinstance(message, dict):
                    raise ValueError('invalid message')
                action = message.get('type')
                if action == 'START':
                    if stream_id is not None:
                        raise DuplicateAudioStream(stream_id)
                    metadata = AudioStreamStart.from_mapping(message)
                    attempted_id = metadata.audio_stream_id
                    await registry.start(metadata, connection_id=connection_id)
                    stream_id = metadata.audio_stream_id
                    deadline = asyncio.get_running_loop().time() + registry.timeout_seconds
                    await websocket.send_json({'type': 'STARTED', 'audio_stream_id': stream_id})
                elif action == 'END':
                    if stream_id is None or message.get('audio_stream_id') != stream_id:
                        raise UnknownAudioStream(message.get('audio_stream_id'))
                    if closed:
                        raise ClosedAudioStream(stream_id)
                    result = await _end_or_disconnect(websocket, registry, stream_id)
                    closed = True
                    await websocket.send_json({'type': 'RESULT', 'audio_stream_id': stream_id, 'result': result})
                else:
                    raise ValueError('invalid message')
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        if closed and isinstance(exc, TimeoutError):
            await websocket.close(code=1000)
            return
        code = 'STREAM_FAILED'
        for kind, reason in (
            (TimeoutError, 'TIMEOUT'), (UnknownAudioStream, 'UNKNOWN_STREAM'),
            (ClosedAudioStream, 'CLOSED_STREAM'), (DuplicateAudioStream, 'DUPLICATE_START'),
            (InvalidAudioStreamStart, 'INVALID_START'), (ValueError, 'INVALID_MESSAGE'),
        ):
            if isinstance(exc, kind):
                code = reason
                break
        if isinstance(exc, (AudioStreamError, ValueError)) and str(exc) in TECHNICAL_REASONS:
            code = str(exc)
        await websocket.send_json({'type': 'ERROR', 'audio_stream_id': stream_id or attempted_id,
                                   'outcome': 'FAILED', 'reason_code': code})
        await websocket.close(code=4400)
    finally:
        await registry.disconnect(connection_id)


async def _end_or_disconnect(websocket, registry, stream_id):
    end_task = asyncio.create_task(registry.end(stream_id))
    receive_task = asyncio.create_task(websocket.receive())
    try:
        done, _ = await asyncio.wait({end_task, receive_task}, return_when=asyncio.FIRST_COMPLETED)
        if receive_task in done:
            frame = receive_task.result()
            if frame['type'] == 'websocket.disconnect':
                raise WebSocketDisconnect(frame.get('code', 1000))
            raise ClosedAudioStream(stream_id)
        return end_task.result()
    finally:
        for task in (end_task, receive_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(end_task, receive_task, return_exceptions=True)
