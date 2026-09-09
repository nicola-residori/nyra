import inspect
import pytest
from pydantic import ValidationError
from shared.protocol.capabilities import CapabilityCorrelation, ExecuteResponse, ResolveCandidate, ResolveResponse, ResolveStatus, ResolvedResource
from shared.protocol.common import CommonOutcome, ErrorDetail
from shared.protocol.execution import ExecutionPlan
from shared.protocol.execution_common import ExecutionStatus, NyraOperation, NyraResourceType, PlanOrigin, PlanValidationState, StepStatus
from shared.protocol.ids import new_request_id, new_trace_id
from skills.execution import ExecutionPlanExecutor, InvalidExecutionPlan

REQUEST_ID = new_request_id()
CORR=CapabilityCorrelation(request_id=REQUEST_ID,origin_request_id=REQUEST_ID,trace_id=new_trace_id())
def step(i,ref,depends_on=None,conditions=None): return {"step_id":i,"operation":NyraOperation.TURN_ON,"target":{"reference":ref,"resource_type":NyraResourceType.LIGHT},"depends_on":depends_on or [],"conditions":conditions or []}
def plan(*steps,state=PlanValidationState.VALIDATED): return ExecutionPlan.model_validate({"plan_id":"p","origin":PlanOrigin.SKILLS,"validation_state":state,"steps":list(steps)})
class Cap:
    def __init__(self,fail=()): self.fail=set(fail); self.resolve_calls=[]; self.execute_calls=[]
    async def resolve(self,reference,trusted_context,*,correlation):
        self.resolve_calls.append(reference.reference); rid="light."+reference.reference.replace(" ","_")
        return ResolveResponse(correlation=correlation,status=ResolveStatus.RESOLVED,reference=reference,candidates=[ResolveCandidate(resource=ResolvedResource(resource_id=rid,resource_type=NyraResourceType.LIGHT,name=reference.reference),score=1)])
    async def execute(self,request,trusted_context):
        self.execute_calls.append(request.resource_id)
        if request.resource_id in self.fail: return ExecuteResponse(correlation=request.correlation,outcome=CommonOutcome.FAILED,error=ErrorDetail(code="TEST_FAILURE"))
        return ExecuteResponse(correlation=request.correlation,outcome=CommonOutcome.SUCCESS)

@pytest.mark.asyncio
async def test_dependency_success_executes_a_then_b():
    c=Cap(); r=await ExecutionPlanExecutor(c).execute(plan(step("a","kitchen"),step("b","desk",["a"])),correlation=CORR,trusted_context={})
    assert c.execute_calls==["light.kitchen","light.desk"]; assert [x.status for x in r.steps]==[StepStatus.COMPLETED,StepStatus.COMPLETED]; assert r.status is ExecutionStatus.COMPLETED
@pytest.mark.asyncio
async def test_failure_skips_dependency_but_independent_c_continues():
    c=Cap(["light.kitchen"]); r=await ExecutionPlanExecutor(c).execute(plan(step("a","kitchen"),step("b","desk",["a"]),step("c","hall")),correlation=CORR,trusted_context={})
    assert {x.step_id:x.status for x in r.steps}=={"a":StepStatus.FAILED,"b":StepStatus.SKIPPED_DEPENDENCY,"c":StepStatus.COMPLETED}; assert c.execute_calls==["light.kitchen","light.hall"]; assert r.status is ExecutionStatus.PARTIALLY_COMPLETED
@pytest.mark.asyncio
async def test_false_condition_skips_without_side_effect():
    c=Cap(); r=await ExecutionPlanExecutor(c).execute(plan(step("a","kitchen",conditions=["false"])),correlation=CORR,trusted_context={})
    assert r.steps[0].status is StepStatus.SKIPPED_CONDITION; assert c.resolve_calls==[]; assert c.execute_calls==[]
@pytest.mark.asyncio
async def test_unvalidated_rejected_before_side_effect():
    c=Cap()
    with pytest.raises(InvalidExecutionPlan): await ExecutionPlanExecutor(c).execute(plan(step("a","kitchen"),state=PlanValidationState.PROPOSED),correlation=CORR,trusted_context={})
    assert c.resolve_calls==[] and c.execute_calls==[]
def test_cycle_rejected_by_contract():
    with pytest.raises(ValidationError): plan(step("a","kitchen",["b"]),step("b","desk",["a"]))
def test_no_direct_ha_transport():
    import skills.execution as module
    src=inspect.getsource(module); assert "/api/states" not in src and "/api/services/" not in src and "home_assistant_token" not in src
