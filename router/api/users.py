from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from router.api.requests import _authorized


router = APIRouter(prefix="/v1/users")


class UserReferenceSync(BaseModel):
    provider: str = Field(min_length=1, max_length=255)
    user_id: str = Field(min_length=1, max_length=1024)
    display_name: str = Field(min_length=1, max_length=255)

    @field_validator("provider", "user_id", "display_name", mode="before")
    @classmethod
    def normalize_required_text(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value


class UserReferenceResponse(BaseModel):
    provider: str
    user_id: str
    display_name: str
    updated_at: datetime


@router.post("/sync", response_model=UserReferenceResponse)
def sync_user_reference(payload: UserReferenceSync, request: Request):
    if not _authorized(request):
        raise HTTPException(status_code=401, detail="unauthorized")
    return request.app.state.user_directory.upsert(
        payload.provider, payload.user_id, payload.display_name
    )
