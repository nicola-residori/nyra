from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .behavior import Behavior
from .execution_common import (
    ExecutionStatus,
    ExecutionStep,
    ExecutionTarget,
    NyraOperation,
    NyraResourceType,
    PlanOrigin,
    PlanValidationState,
    ResolvedTarget,
    StepStatus,
)

class ExecutionPlan(BaseModel):
    model_config=ConfigDict(extra="forbid")
    plan_id: str
    origin: PlanOrigin
    validation_state: PlanValidationState
    steps: list[ExecutionStep]
    behaviors: list[Behavior] = Field(default_factory=list)

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
