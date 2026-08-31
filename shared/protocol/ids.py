from __future__ import annotations
import re
import secrets
import string
from uuid import UUID, uuid4
from pydantic import BaseModel, field_validator

SPAN_RE = re.compile(r"^[A-Z0-9_-]+#[a-z0-9_]+#[A-Z0-9]{8}$")

def _new_prefixed_uuid(prefix: str) -> str:
    return f"{prefix}_{uuid4()}"

def new_session_id() -> str:
    return _new_prefixed_uuid("ses")

def new_request_id() -> str:
    return _new_prefixed_uuid("req")

def new_trace_id() -> str:
    return _new_prefixed_uuid("trc")

def _normalize_component(value: str) -> str:
    return re.sub(r"[^A-Z0-9_-]+", "_", value.upper()).strip("_") or "UNKNOWN"

def _normalize_operation(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_") or "operation"

def new_span_id(component: str, operation: str) -> str:
    alphabet = string.ascii_uppercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{_normalize_component(component)}#{_normalize_operation(operation)}#{suffix}"

def validate_prefixed_uuid(value: str | None, prefix: str) -> str | None:
    if value is None:
        return None
    marker = f"{prefix}_"
    if not value.startswith(marker):
        raise ValueError(f"expected {marker}UUIDv4")
    try:
        parsed = UUID(value[len(marker):])
    except ValueError as exc:
        raise ValueError(f"invalid {prefix} UUID") from exc
    if parsed.version != 4 or str(parsed) != value[len(marker):]:
        raise ValueError(f"invalid {prefix} UUIDv4")
    return value

class CorrelationContext(BaseModel):
    request_id: str | None = None
    origin_request_id: str | None = None
    trace_id: str
    parent_span_id: str | None = None

    @field_validator("request_id", "origin_request_id")
    @classmethod
    def validate_request_ids(cls, value: str | None) -> str | None:
        return validate_prefixed_uuid(value, "req")

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, value: str) -> str:
        validated = validate_prefixed_uuid(value, "trc")
        assert validated is not None
        return validated

    @field_validator("parent_span_id")
    @classmethod
    def validate_parent_span_id(cls, value: str | None) -> str | None:
        if value is not None and not SPAN_RE.fullmatch(value):
            raise ValueError("invalid span id")
        return value
