from enum import Enum
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .execution import ExecutionStep

class BehaviorLifecycle(str, Enum):
    ONE_SHOT="ONE_SHOT"; PERSISTENT="PERSISTENT"
class BehaviorActionType(str, Enum):
    ACTION="ACTION"; DELAY="DELAY"; WAIT_CONDITION="WAIT_CONDITION"
class WaitTimeoutAction(str, Enum):
    STOP="STOP"; CONTINUE="CONTINUE"
class BehaviorTrigger(BaseModel):
    model_config=ConfigDict(extra="forbid")
    kind: str
    expression: str
class BehaviorCondition(BaseModel):
    model_config=ConfigDict(extra="forbid")
    kind: str
    expression: str
class BehaviorAction(BaseModel):
    model_config=ConfigDict(extra="forbid")
    type: BehaviorActionType
    action: ExecutionStep | None = None
    delay_seconds: float | None = Field(default=None, ge=0)
    condition: BehaviorCondition | None = None
    timeout_seconds: float | None = Field(default=None, ge=0)
    on_timeout: WaitTimeoutAction = WaitTimeoutAction.STOP
    @model_validator(mode="after")
    def _type_payload(self):
        if self.type is BehaviorActionType.ACTION and self.action is None: raise ValueError("ACTION requires action")
        if self.type is BehaviorActionType.DELAY and self.delay_seconds is None: raise ValueError("DELAY requires delay_seconds")
        if self.type is BehaviorActionType.WAIT_CONDITION and self.condition is None: raise ValueError("WAIT_CONDITION requires condition")
        return self
class Behavior(BaseModel):
    """Platform-neutral behavior: triggers use OR, conditions use AND, actions run sequentially."""
    model_config=ConfigDict(extra="forbid")
    behavior_id: str
    lifecycle: BehaviorLifecycle
    triggers: list[BehaviorTrigger] = Field(default_factory=list, description="Triggers are combined with OR semantics.")
    conditions: list[BehaviorCondition] = Field(default_factory=list, description="Conditions are combined with AND semantics.")
    actions: list[BehaviorAction] = Field(default_factory=list, description="Actions execute sequentially.")
