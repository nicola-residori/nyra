from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from shared.protocol.ids import validate_prefixed_uuid
from shared.protocol.requests import CloseReason, RequestSource


class InteractionState(StrEnum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    IDENTIFYING = "IDENTIFYING"
    PROCESSING_LOCAL = "PROCESSING_LOCAL"
    PROCESSING_GLOBAL = "PROCESSING_GLOBAL"
    USING_TOOL = "USING_TOOL"
    WAITING_CLARIFICATION = "WAITING_CLARIFICATION"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"


class IdentityFeedback(StrEnum):
    RECOGNIZED = "RECOGNIZED"
    NOT_RECOGNIZED = "NOT_RECOGNIZED"
    IDENTITY_CHANGED = "IDENTITY_CHANGED"


class EventCategory(StrEnum):
    INTERACTION_STATE = "interaction_state"
    IDENTITY = "identity"
    SESSION = "session"


class _CorrelationModel(BaseModel):
    session_id: str | None = None
    request_id: str | None = None
    trace_id: str | None = None

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


class InteractionStateChanged(_CorrelationModel):
    event: str = "INTERACTION_STATE_CHANGED"
    category: EventCategory = EventCategory.INTERACTION_STATE
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state: InteractionState
    source: RequestSource | None = None


class IdentityFeedbackEvent(_CorrelationModel):
    event: str = "IDENTITY_FEEDBACK"
    category: EventCategory = EventCategory.IDENTITY
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    feedback: IdentityFeedback
    source: RequestSource | None = None


class SessionClosedEvent(_CorrelationModel):
    event: str = "SESSION_CLOSED"
    category: EventCategory = EventCategory.SESSION
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    close_reason: CloseReason
    source: RequestSource | None = None


class EventSubscription(BaseModel):
    action: str = "subscribe"
    categories: set[EventCategory]


class StateSnapshot(_CorrelationModel):
    source_id: str | None = None
    state: InteractionState
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
