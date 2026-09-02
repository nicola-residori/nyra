from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator

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

class ExecutionPlan(BaseModel):
    model_config=ConfigDict(extra="forbid")
    plan_id: str
    origin: PlanOrigin
    validation_state: PlanValidationState
    steps: list[ExecutionStep]

    @model_validator(mode="after")
    def _validate_graph(self):
        ids=[step.step_id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("step_id values must be unique")
        known=set(ids)
        graph={step.step_id:set(step.depends_on) for step in self.steps}
        for node,deps in graph.items():
            if node in deps:
                raise ValueError("step cannot depend on itself")
            if not deps <= known:
                raise ValueError("dependencies must reference existing steps")
        visiting=set(); visited=set()
        def visit(node):
            if node in visiting: raise ValueError("dependency graph must be acyclic")
            if node in visited: return
            visiting.add(node)
            for dep in graph[node]: visit(dep)
            visiting.remove(node); visited.add(node)
        for node in graph: visit(node)
        return self

class StepResult(BaseModel):
    model_config=ConfigDict(extra="forbid")
    step_id: str
    status: StepStatus
    result: dict[str, Any] | None = None
    error: str | None = None

class ExecutionResult(BaseModel):
    model_config=ConfigDict(extra="forbid")
    plan_id: str
    status: ExecutionStatus
    steps: list[StepResult] = Field(default_factory=list)
