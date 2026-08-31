from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class SemanticConfidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: float = Field(ge=0.0, le=1.0)
    label: str | None = None

class SemanticTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference: str
    kind: str | None = None

class SemanticParameter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    value: Any
    unit: str | None = None
    expression: str | None = None

class SemanticAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str
    target: SemanticTarget | None = None
    parameters: list[SemanticParameter] = Field(default_factory=list)

class SemanticTemporal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression: str
    relation: str | None = None

class SemanticTrigger(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    expression: str

class SemanticCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    expression: str

class SemanticResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: str
    domain: str | None = None
    actions: list[SemanticAction] = Field(default_factory=list)
    temporal: SemanticTemporal | None = None
    triggers: list[SemanticTrigger] = Field(default_factory=list)
    conditions: list[SemanticCondition] = Field(default_factory=list)
    confidence: SemanticConfidence | None = None
    interpretation: str | None = None
