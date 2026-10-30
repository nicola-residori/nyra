from fastapi import APIRouter, Request
from shared.protocol.music import MusicRequest

router = APIRouter()


@router.post("/v1/capabilities/music")
async def music(payload: MusicRequest, request: Request):
    return await request.app.state.music_capability.music(payload)
