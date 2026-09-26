from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .execution import ExecutionPlan
from .execution_common import PlanOrigin, PlanValidationState


class LlmPurpose(str, Enum):
    SEMANTIC = "SEMANTIC"
    REASONING = "REASONING"
    MEMORY_EXTRACTION = "MEMORY_EXTRACTION"


class ReasoningOutcome(str, Enum):
    COMPLETED = "COMPLETED"
    NEEDS_CAPABILITY = "NEEDS_CAPABILITY"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    FAILED = "FAILED"


class ReasoningCapability(str, Enum):
    SEARCH_MEMORY = "SEARCH_MEMORY"
    READ_STATE = "READ_STATE"
    READ_ATTRIBUTE = "READ_ATTRIBUTE"
    DISCOVER_RESOURCES = "DISCOVER_RESOURCES"


class CapabilityStatus(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ReasoningContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str
    current_user_input: str
    trusted_identity: dict[str, Any] | None = None
    policy: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    area: str | None = None
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    clarification: dict[str, Any] | None = None
    operational: dict[str, Any] = Field(default_factory=dict)


class CapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability: ReasoningCapability
    parameters: dict[str, Any] = Field(default_factory=dict)
    functional_reason: str | None = None


class CapabilityResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capability_call_id: str
    capability: ReasoningCapability
    status: CapabilityStatus
    data: dict[str, Any] | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _validate_status_payload(self):
        if self.status is CapabilityStatus.FAILED and not self.error:
            raise ValueError("failed capability result requires error")
        if self.status is CapabilityStatus.COMPLETED and self.error is not None:
            raise ValueError("completed capability result cannot carry error")
        return self


class ClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str
    reason: str | None = None


class ReasoningError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    category: str
    message: str | None = None


class UsageMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_cost: float | None = Field(default=None, ge=0)


class LlmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purpose: LlmPurpose
    context: ReasoningContext
    capability_results: list[CapabilityResult] = Field(default_factory=list)
    reasoning_id: str | None = None

    @model_validator(mode="after")
    def _validate_purpose_state(self):
        if self.purpose is LlmPurpose.SEMANTIC:
            if self.reasoning_id is not None:
                raise ValueError("SEMANTIC requests cannot carry reasoning_id")
            if self.capability_results:
                raise ValueError("SEMANTIC requests cannot carry capability results")
        return self


class ReasoningResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: ReasoningOutcome
    reasoning_id: str
    response_text: str | None = None
    capability_request: CapabilityRequest | None = None
    clarification: ClarificationRequest | None = None
    proposed_execution_plan: ExecutionPlan | None = None
    error: ReasoningError | None = None
    usage: UsageMetadata | None = None

    @model_validator(mode="after")
    def _validate_outcome_payload(self):
        if self.proposed_execution_plan is not None:
            if self.outcome is not ReasoningOutcome.COMPLETED:
                raise ValueError("execution plan is only valid for COMPLETED")
            if self.proposed_execution_plan.origin is not PlanOrigin.REASONING_LLM:
                raise ValueError("LLM execution plan must originate from REASONING_LLM")
            if self.proposed_execution_plan.validation_state is not PlanValidationState.PROPOSED:
                raise ValueError("LLM execution plan must remain PROPOSED")

        required = {
            ReasoningOutcome.NEEDS_CAPABILITY: self.capability_request,
            ReasoningOutcome.NEEDS_CLARIFICATION: self.clarification,
            ReasoningOutcome.FAILED: self.error,
        }
        if self.outcome in required and required[self.outcome] is None:
            raise ValueError(f"{self.outcome.value} requires its outcome payload")

        if self.outcome is not ReasoningOutcome.NEEDS_CAPABILITY and self.capability_request is not None:
            raise ValueError("capability_request only valid for NEEDS_CAPABILITY")
        if self.outcome is not ReasoningOutcome.NEEDS_CLARIFICATION and self.clarification is not None:
            raise ValueError("clarification only valid for NEEDS_CLARIFICATION")
        if self.outcome is not ReasoningOutcome.FAILED and self.error is not None:
            raise ValueError("error only valid for FAILED")
        if self.outcome is not ReasoningOutcome.COMPLETED and (
            self.response_text is not None or self.proposed_execution_plan is not None
        ):
            raise ValueError("completion payload only valid for COMPLETED")
        return self
