from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .ids import validate_prefixed_uuid

class RequestType(str, Enum):
    HA_ASSIST = "ha_assist"
    HA_SPEAKER = "ha_speaker"
    JOB = "job"
    NYRA_UI = "nyra_ui"

class IdentityResolutionSource(str, Enum):
    TRUSTED_HA_IDENTITY = "TRUSTED_HA_IDENTITY"
    SPEAKER_IDENTIFICATION = "SPEAKER_IDENTIFICATION"
    SESSION_CONTINUITY = "SESSION_CONTINUITY"
    GUEST_FALLBACK = "GUEST_FALLBACK"

class ResolvedIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: str
    resolution_source: IdentityResolutionSource

class TemporalContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict[str, Any] = Field(default_factory=dict)

class OperationalContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict[str, Any] = Field(default_factory=dict)

class PolicyContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict[str, Any] = Field(default_factory=dict)

class ClarificationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pending: bool = False
    values: dict[str, Any] = Field(default_factory=dict)

class LifecycleContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict[str, Any] = Field(default_factory=dict)

class RequestContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str | None = None
    request_id: str | None = None
    origin_request_id: str | None = None
    trace_id: str
    type: RequestType
    language: str
    source: str | None = None
    area: str | None = None
    identity: ResolvedIdentity | None = None
    temporal: TemporalContext | None = None
    operational: OperationalContext | None = None
    policy: PolicyContext | None = None
    clarification: ClarificationContext | None = None
    lifecycle: LifecycleContext | None = None

    @field_validator("session_id")
    @classmethod
    def _session(cls, value):
        return validate_prefixed_uuid(value, "ses") if value is not None else value

    @field_validator("request_id", "origin_request_id")
    @classmethod
    def _request(cls, value):
        return validate_prefixed_uuid(value, "req") if value is not None else value

    @field_validator("trace_id")
    @classmethod
    def _trace(cls, value):
        return validate_prefixed_uuid(value, "trc")

    @model_validator(mode="after")
    def _interactive_ids(self):
        if self.type is not RequestType.JOB and (self.session_id is None or self.request_id is None):
            raise ValueError("interactive requests require session_id and request_id")
        if self.type is RequestType.JOB and (self.session_id is not None or self.request_id is not None):
            raise ValueError("job requests must not carry session_id or request_id")
        return self
