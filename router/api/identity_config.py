from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/v1/config/identity", tags=["identity-config"])


class IdentityTimeoutUpdate(BaseModel):
    identification_timeout_seconds: float = Field(gt=0)


def _payload(snapshot):
    return {
        "identification_timeout_seconds": snapshot.identification_timeout_seconds,
        "revision": snapshot.revision,
    }


@router.get("")
async def get_identity_config(request: Request):
    return _payload(request.app.state.identity_config.snapshot())


@router.put("")
async def put_identity_config(payload: IdentityTimeoutUpdate, request: Request):
    snapshot = request.app.state.identity_config.update_identification_timeout(
        payload.identification_timeout_seconds
    )
    return _payload(snapshot)
