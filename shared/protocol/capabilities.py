from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from .common import CommonOutcome, ErrorDetail
from .execution import NyraOperation, NyraResourceType
from .ids import CorrelationContext

class CapabilityCorrelation(CorrelationContext):
    pass
class ResolveCardinality(str, Enum):
    ONE="ONE"; MANY="MANY"
class ResolveStatus(str, Enum):
    RESOLVED="RESOLVED"; AMBIGUOUS="AMBIGUOUS"; NOT_FOUND="NOT_FOUND"
class ResourceReference(BaseModel):
    model_config=ConfigDict(extra="forbid")
    reference: str
    resource_type: NyraResourceType | None = None
    cardinality: ResolveCardinality = ResolveCardinality.ONE
class ResolvedResource(BaseModel):
    model_config=ConfigDict(extra="forbid")
    resource_id: str
    resource_type: NyraResourceType
    name: str | None = None
class ResolveCandidate(BaseModel):
    model_config=ConfigDict(extra="forbid")
    resource: ResolvedResource
    score: float | None = None
class ResolveResponse(BaseModel):
    model_config=ConfigDict(extra="forbid")
    correlation: CapabilityCorrelation
    status: ResolveStatus
    reference: ResourceReference
    candidates: list[ResolveCandidate] = Field(default_factory=list)
class ExecuteRequest(BaseModel):
    model_config=ConfigDict(extra="forbid")
    correlation: CapabilityCorrelation
    operation: NyraOperation
    resource_id: str
    resource_type: NyraResourceType
    parameters: dict[str, Any] = Field(default_factory=dict)
class ExecuteResponse(BaseModel):
    model_config=ConfigDict(extra="forbid")
    correlation: CapabilityCorrelation
    outcome: CommonOutcome
    result: dict[str, Any] | None = None
    error: ErrorDetail | None = None
_IDEMPOTENT={NyraOperation.TURN_ON,NyraOperation.TURN_OFF,NyraOperation.OPEN,NyraOperation.CLOSE,NyraOperation.SET}
def is_idempotent_operation(operation: NyraOperation) -> bool:
    return operation in _IDEMPOTENT
