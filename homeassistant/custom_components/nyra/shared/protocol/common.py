from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict

class CommonOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"

class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str | None = None
    details: dict[str, Any] | None = None
