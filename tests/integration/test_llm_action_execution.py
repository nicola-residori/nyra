import pytest
from router.plan_execution import RouterPlanExecutor
from shared.protocol.capabilities import CapabilityCorrelation,ResolveResponse,ResolveStatus,ResolveCandidate,ResolvedResource,ExecuteResponse
from shared.protocol.common import CommonOutcome
from shared.protocol.execution import ExecutionPlan
from shared.protocol.execution_common import ExecutionStep,ExecutionTarget,NyraOperation,NyraResourceType,PlanOrigin,PlanValidationState,ExecutionStatus
from shared.protocol.ids import new_request_id, new_trace_id

def corr(): return CapabilityCorrelation(request_id=(rid:=new_request_id()),origin_request_id=rid,trace_id=new_trace_id())
def plan():
 return ExecutionPlan(plan_id="p",origin=PlanOrigin.REASONING_LLM,validation_state=PlanValidationState.VALIDATED,steps=[ExecutionStep(step_id="s",operation=NyraOperation.TURN_ON,target=ExecutionTarget(reference="kitchen",resource_type=NyraResourceType.LIGHT))])

@pytest.mark.asyncio
async def test_router_executes_only_validated_plan_resolve_then_execute():
 calls=[]
 class Cap:
  async def resolve(self,reference,trusted_context,*,correlation):
   calls.append("resolve"); return ResolveResponse(correlation=correlation,status=ResolveStatus.RESOLVED,reference=reference,candidates=[ResolveCandidate(resource=ResolvedResource(resource_id="light.kitchen",resource_type=NyraResourceType.LIGHT))])
  async def execute(self,request,trusted_context):
   calls.append("execute"); return ExecuteResponse(correlation=request.correlation,outcome=CommonOutcome.SUCCESS)
 r=await RouterPlanExecutor(Cap()).execute(plan(),correlation=corr(),trusted_context={})
 assert r.status is ExecutionStatus.COMPLETED and calls==["resolve","execute"]

@pytest.mark.asyncio
async def test_router_refuses_proposed_plan_before_capability():
 class Never:
  async def resolve(self,*a,**k): raise AssertionError
  async def execute(self,*a,**k): raise AssertionError
 with pytest.raises(ValueError):
  await RouterPlanExecutor(Never()).execute(plan().model_copy(update={"validation_state":PlanValidationState.PROPOSED}),correlation=corr(),trusted_context={})
