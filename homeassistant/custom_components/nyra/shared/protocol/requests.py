from __future__ import annotations
from uuid import UUID
from enum import StrEnum
from typing import Any
from shared.protocol.ids import validate_prefixed_uuid
from pydantic import BaseModel, Field, field_validator, model_validator


class ExecutionType(StrEnum):
    HA_SPEAKER = "ha_speaker"
    HA_ASSIST = "ha_assist"
    JOB = "job"
    NYRA_UI = "nyra_ui"


class RequestStatus(StrEnum):
    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    CLOSED = "closed"
    FAILED = "failed"
    EXPIRED = "expired"


class CloseReason(StrEnum):
    EXPLICIT_CLOSE = "explicit_close"
    DIRECT_COMMAND = "direct_command"
    ALARM_DISMISSED = "alarm_dismissed"
    TIMEOUT = "timeout"
    POLICY = "policy"


def validate_prefixed_uuid(value: str | None, prefix: str) -> str | None:
    if value is None:
        return None
    marker = prefix + "_"
    if not value.startswith(marker):
        raise ValueError(f"expected {marker}UUID")
    try:
        UUID(value[len(marker):])
    except ValueError as exc:
        raise ValueError(f"invalid {prefix} UUID") from exc
    return value


class RequestSource(BaseModel):
    id: str
    area: str | None = None


class TrustedIdentity(BaseModel):
    user_id: str
    provider: str
    confidence: float = Field(ge=0.0, le=1.0)


class RequestInput(BaseModel):
    text: str = Field(min_length=1)


class NyraRequest(BaseModel):
    type: ExecutionType
    session_id: str | None = None
    request_id: str | None = None
    origin_request_id: str | None = None
    language: str = Field(min_length=2)
    source: RequestSource | None = None
    identity: TrustedIdentity | None = None
    input: RequestInput

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value):
        return validate_prefixed_uuid(value, "ses")

    @field_validator("request_id", "origin_request_id")
    @classmethod
    def validate_request_ids(cls, value):
        return validate_prefixed_uuid(value, "req")

    @model_validator(mode="after")
    def validate_execution_ids(self):
        if self.type is ExecutionType.JOB:
            if self.session_id is not None or self.request_id is not None:
                raise ValueError("job executions must not contain session_id or request_id")
        elif self.session_id is None or self.request_id is None:
            raise ValueError("user requests require session_id and request_id")
        return self


class NyraResponseBody(BaseModel):
    text: str


class NyraRequestResponse(BaseModel):
    status: RequestStatus
    session_id: str | None = None
    request_id: str | None = None
    trace_id: str
    response: NyraResponseBody | None = None
    close_reason: CloseReason | None = None
    error: dict[str, Any] | None = None

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value):
        return validate_prefixed_uuid(value, "ses")

    @field_validator("request_id")
    @classmethod
    def validate_request_id(cls, value):
        return validate_prefixed_uuid(value, "req")

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, value):
        return validate_prefixed_uuid(value, "trc")

    @model_validator(mode="after")
    def validate_close(self):
        if self.status is RequestStatus.CLOSED and self.close_reason is None:
            raise ValueError("closed responses require close_reason")
        if self.status is not RequestStatus.CLOSED and self.close_reason is not None:
            raise ValueError("close_reason is only valid for closed responses")
        return self
