from __future__ import annotations
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import re
from pydantic import BaseModel, Field, field_validator
from shared.protocol.requests import validate_prefixed_uuid

SPAN_RE = re.compile(r"^[A-Z0-9_-]+#[a-z0-9_]+#[A-Z0-9]{8}$")

class LogLevel(StrEnum):
    TRACE="TRACE"; DEBUG="DEBUG"; INFO="INFO"; WARN="WARN"; ERROR="ERROR"; CRITICAL="CRITICAL"

class LogKind(StrEnum):
    REQUEST="REQUEST"; RESPONSE="RESPONSE"; FAULT="FAULT"; EVENT="EVENT"

class LogRecord(BaseModel):
    schema_version: int = 1
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ct: str
    level: LogLevel
    kind: LogKind
    event: str
    session_id: str | None = None
    request_id: str | None = None
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    origin_request_id: str | None = None
    operation: str | None = None
    result: str | None = None
    message: str | None = None
    session_elapsed_ms: float | None = None
    request_elapsed_ms: float | None = None
    trace_elapsed_ms: float | None = None
    span_elapsed_ms: float | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    payload: Any = None

    @field_validator("schema_version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value != 1:
            raise ValueError("unsupported schema version")
        return value

    @field_validator("event")
    @classmethod
    def validate_event(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("event is required")
        return value

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str | None) -> str | None:
        return validate_prefixed_uuid(value, "ses")

    @field_validator("request_id", "origin_request_id")
    @classmethod
    def validate_request_ids(cls, value: str | None) -> str | None:
        return validate_prefixed_uuid(value, "req")

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, value: str) -> str:
        return validate_prefixed_uuid(value, "trc")

    @field_validator("span_id", "parent_span_id")
    @classmethod
    def validate_span(cls, value: str | None) -> str | None:
        if value is not None and not SPAN_RE.fullmatch(value):
            raise ValueError("invalid span id")
        return value

class LogBatch(BaseModel):
    records: list[LogRecord]
