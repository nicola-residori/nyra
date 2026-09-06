from fastapi import APIRouter, WebSocket

from router.api.events import _authorized
from shared.audio_websocket import serve_audio
from shared.protocol.ids import new_span_id, new_trace_id

router = APIRouter(prefix='/v1')


def _add_router_correlation(message: dict) -> dict:
    enriched = dict(message)
    enriched["trace_id"] = new_trace_id()
    enriched["span_id"] = new_span_id("ROUTER", "audio_relay")
    return enriched


@router.websocket('/audio/stream')
async def audio_stream(websocket: WebSocket):
    if not _authorized(websocket):
        await websocket.close(code=4401)
        return
    await serve_audio(
        websocket,
        websocket.app.state.audio_streams,
        transform_start=_add_router_correlation,
    )
