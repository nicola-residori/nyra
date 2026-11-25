"""Source-addressed deferred audio contract; acceptance is not completion."""

from enum import Enum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .capabilities import CapabilityCorrelation


class AlertState(str, Enum):
    NOT_FOUND = "NOT_FOUND"
    OFFLINE = "OFFLINE"
    BUSY = "BUSY"
    ACCEPTED = "ACCEPTED"
    PLAYING = "PLAYING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"
    FAILED = "FAILED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"


class AlertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Literal["START", "STATUS", "STOP"]
    job_id: str = Field(pattern=r"^job_[A-Za-z0-9_-]{1,80}$")
    source_id: str = Field(min_length=1, max_length=255)
    correlation: CapabilityCorrelation | None = None
    alert_kind: Literal["alarm", "timer", "call", "notification"] = "timer"
    language: str = "it"
    message: str | None = Field(default=None, max_length=1000)
    max_seconds: int = Field(default=60, ge=1, le=60)

    @model_validator(mode="after")
    def validate_call(self):
        if (
            self.action == "START"
            and self.alert_kind in ("call", "notification")
            and not self.message
        ):
            raise ValueError("call requires message")
        return self


class AlertResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: AlertState
    error: str | None = None
