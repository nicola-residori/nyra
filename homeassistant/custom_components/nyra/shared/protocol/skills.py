from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import ErrorDetail
from .ids import CorrelationContext
from .memory import MemoryRequirement


class SkillOutcome(str, Enum):
    HANDLED = "HANDLED"
    MISS = "MISS"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    FAILED = "FAILED"


class JobStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    CANCELLED = "CANCELLED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"
    UNKNOWN_OUTCOME = "UNKNOWN_OUTCOME"


class SkillCorrelation(CorrelationContext):
    pass


class SkillMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    matched: bool
    skill_name: str | None = None
    token: str | None = None
    memory_requirement: MemoryRequirement = MemoryRequirement.NONE
    memory_query: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SkillCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correlation: SkillCorrelation
    text: str
    language: str
    context: dict[str, Any] = Field(default_factory=dict)
    pending_state: dict[str, Any] | None = None


class SkillCheckResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correlation: SkillCorrelation
    outcome: SkillOutcome
    match: SkillMatch | None = None
    error: ErrorDetail | None = None


class SkillExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correlation: SkillCorrelation
    match: SkillMatch
    text: str
    language: str
    context: dict[str, Any] = Field(default_factory=dict)
    memory: dict[str, Any] | None = None
    pending_state: dict[str, Any] | None = None


class SkillExecuteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correlation: SkillCorrelation
    outcome: SkillOutcome
    text: str | None = None
    result: dict[str, Any] | None = None
    pending_state: dict[str, Any] | None = None
    error: ErrorDetail | None = None
