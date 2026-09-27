from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .common import ErrorDetail
from .ids import CorrelationContext
from .memory import MemoryRequirement
from .execution import ExecutionPlan
from .execution_common import PlanOrigin, PlanValidationState
from .semantic import SemanticResult


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



class PlanValidationOutcome(str, Enum):
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"

class PlanValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correlation: SkillCorrelation
    plan: ExecutionPlan
    trusted_context: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _proposal_only(self):
        if self.plan.origin is not PlanOrigin.REASONING_LLM:
            raise ValueError("plan validation accepts only REASONING_LLM origin")
        if self.plan.validation_state is not PlanValidationState.PROPOSED:
            raise ValueError("plan validation accepts only PROPOSED plans")
        return self

class PlanValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correlation: SkillCorrelation
    outcome: PlanValidationOutcome
    plan: ExecutionPlan | None = None
    error: ErrorDetail | None = None

    @model_validator(mode="after")
    def _shape(self):
        if self.outcome is PlanValidationOutcome.VALIDATED:
            if self.plan is None or self.plan.validation_state is not PlanValidationState.VALIDATED:
                raise ValueError("VALIDATED response requires VALIDATED plan")
        elif self.error is None:
            raise ValueError("REJECTED response requires error")
        return self


class SkillCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    correlation: SkillCorrelation
    text: str
    language: str
    context: dict[str, Any] = Field(default_factory=dict)
    pending_state: dict[str, Any] | None = None
    semantic: SemanticResult | None = None


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
