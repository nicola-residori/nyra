from fastapi import APIRouter, HTTPException, Request
from shared.protocol.requests import NyraRequest, NyraRequestResponse
from router.lifecycle.service import LifecycleConflict

router = APIRouter(prefix="/v1")


def _authorized(request: Request) -> bool:
    token = request.app.state.settings.ingress_token
    if not token:
        return True
    return request.headers.get("authorization") == f"Bearer {token}"


@router.post("/requests", response_model=NyraRequestResponse)
async def execute_request(payload: NyraRequest, request: Request):
    if not _authorized(request):
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        return await request.app.state.lifecycle.execute(payload)
    except LifecycleConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
