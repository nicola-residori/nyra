from fastapi import APIRouter, WebSocket

from router.api.events import _authorized
from shared.audio_websocket import serve_audio

router = APIRouter(prefix='/v1')


@router.websocket('/audio/stream')
async def audio_stream(websocket: WebSocket):
    if not _authorized(websocket):
        await websocket.close(code=4401)
        return
    await serve_audio(websocket, websocket.app.state.audio_streams)
