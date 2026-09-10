from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class NyraOperation(str, Enum):
    TURN_ON="TURN_ON"; TURN_OFF="TURN_OFF"; OPEN="OPEN"; CLOSE="CLOSE"; TOGGLE="TOGGLE"; SET="SET"; INCREASE="INCREASE"; DECREASE="DECREASE"; START="START"; STOP="STOP"; TRIGGER="TRIGGER"

class NyraResourceType(str, Enum):
    LIGHT="LIGHT"; SWITCH="SWITCH"; COVER="COVER"; CLIMATE="CLIMATE"; MEDIA_PLAYER="MEDIA_PLAYER"; SCRIPT="SCRIPT"; SCENE="SCENE"; AUTOMATION="AUTOMATION"

class PlanOrigin(str, Enum):
    REASONING_LLM="REASONING_LLM"; SKILLS="SKILLS"

class PlanValidationState(str, Enum):
    PROPOSED="PROPOSED"; VALIDATED="VALIDATED"

class StepStatus(str, Enum):
    COMPLETED="COMPLETED"; FAILED="FAILED"; SKIPPED_DEPENDENCY="SKIPPED_DEPENDENCY"; SKIPPED_CONDITION="SKIPPED_CONDITION"

class ExecutionStatus(str, Enum):
    COMPLETED="COMPLETED"; PARTIALLY_COMPLETED="PARTIALLY_COMPLETED"

class ResolvedTarget(BaseModel):
    model_config=ConfigDict(extra="forbid")
    resource_id: str
    resource_type: NyraResourceType
    semantic_reference: str

class ExecutionTarget(BaseModel):
    model_config=ConfigDict(extra="forbid")
    reference: str
    resource_type: NyraResourceType
    resolved: ResolvedTarget | None = None

class ExecutionStep(BaseModel):
    model_config=ConfigDict(extra="forbid")
    step_id: str
    operation: NyraOperation
    target: ExecutionTarget
    parameters: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
