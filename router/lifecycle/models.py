from __future__ import annotations
from datetime import datetime
from typing import Any
from pydantic import BaseModel
from shared.protocol.requests import ExecutionType, RequestSource, RequestStatus


class PersistedRequestState(BaseModel):
    request_id: str
    session_id: str
    type: ExecutionType
    language: str
    source: RequestSource | None = None
    identity_user_id: str | None = None
    original_input: str
    status: RequestStatus
    current_trace_id: str
    pending_state: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None = None
