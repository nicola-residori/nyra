from fastapi import APIRouter, Request
from shared.protocol.alerts import AlertRequest, AlertResponse

router = APIRouter()


@router.post("/v1/capabilities/audio", response_model=AlertResponse)
async def audio_capability(payload: AlertRequest, request: Request):
    return await request.app.state.alert_capability.alert(payload)
