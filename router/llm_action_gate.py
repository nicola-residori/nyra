from __future__ import annotations
from typing import Any,Protocol
from shared.protocol.execution import ExecutionPlan
from shared.protocol.execution_common import PlanOrigin,PlanValidationState
from shared.protocol.skills import PlanValidationOutcome

class SkillsPlanPort(Protocol):
    async def validate_plan(self,plan:ExecutionPlan,*,correlation,trusted_context:dict[str,Any]): ...

class LlmActionGate:
    def __init__(self,skills_plan_port:SkillsPlanPort): self.skills_plan_port=skills_plan_port
    async def validate_proposal(self,plan:ExecutionPlan,*,correlation,trusted_context:dict[str,Any])->ExecutionPlan:
        if plan.origin is not PlanOrigin.REASONING_LLM: raise ValueError("LLM action gate accepts only LLM-origin plans")
        if plan.validation_state is not PlanValidationState.PROPOSED: raise ValueError("LLM action gate accepts only PROPOSED plans")
        response=await self.skills_plan_port.validate_plan(plan,correlation=correlation,trusted_context=trusted_context)
        if response.outcome is not PlanValidationOutcome.VALIDATED or response.plan is None:
            code=response.error.code if response.error else "PLAN_REJECTED"
            raise ValueError(code)
        return response.plan
