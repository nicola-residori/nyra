from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field
from shared.protocol.requests import ExecutionType, RequestSource, RequestStatus


class PersistedRequestState(BaseModel):
    request_id: str
    session_id: str
    type: ExecutionType
    language: str
    source: RequestSource | None = None
    identity_user_id: str | None = None
    last_trusted_user_id: str | None = None
    original_input: str
    response_text: str | None = None
    conversation_turns: list[dict[str, str]] = Field(default_factory=list)
    status: RequestStatus
    current_trace_id: str
    pending_state: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
