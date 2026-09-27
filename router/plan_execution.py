from __future__ import annotations
from shared.protocol.capabilities import ExecuteRequest,ResolveCardinality,ResourceReference
from shared.protocol.common import CommonOutcome
from shared.protocol.execution import ExecutionResult,StepResult
from shared.protocol.execution_common import ExecutionStatus,PlanValidationState,StepStatus
from shared.protocol.capabilities import ResolveStatus

class RouterPlanExecutor:
    def __init__(self,capability): self.capability=capability
    async def execute(self,plan,*,correlation,trusted_context):
        if plan.validation_state is not PlanValidationState.VALIDATED:
            raise ValueError("Router executes only VALIDATED plans")
        results=[]
        for step in plan.steps:
            resolved=step.target.resolved
            if resolved is None:
                rr=await self.capability.resolve(ResourceReference(reference=step.target.reference,resource_type=step.target.resource_type,cardinality=ResolveCardinality.ONE),trusted_context,correlation=correlation)
                if rr.status is not ResolveStatus.RESOLVED or len(rr.candidates)!=1:
                    results.append(StepResult(step_id=step.step_id,status=StepStatus.FAILED,error=f"RESOLVE_{rr.status.value}")); continue
                resource=rr.candidates[0].resource
                rid,rtype=resource.resource_id,resource.resource_type
            else:
                rid,rtype=resolved.resource_id,resolved.resource_type
            response=await self.capability.execute(ExecuteRequest(correlation=correlation,operation=step.operation,resource_id=rid,resource_type=rtype,parameters=step.parameters),trusted_context)
            results.append(StepResult(step_id=step.step_id,status=StepStatus.COMPLETED if response.outcome is CommonOutcome.SUCCESS else StepStatus.FAILED,error=None if response.outcome is CommonOutcome.SUCCESS else (response.error.code if response.error else response.outcome.value)))
        status=ExecutionStatus.COMPLETED if all(x.status is StepStatus.COMPLETED for x in results) else ExecutionStatus.PARTIALLY_COMPLETED
        return ExecutionResult(plan_id=plan.plan_id,status=status,steps=results)
