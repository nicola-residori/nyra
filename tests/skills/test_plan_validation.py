import pytest
from shared.protocol.execution import ExecutionPlan
from shared.protocol.execution_common import ExecutionStep,ExecutionTarget,NyraOperation,NyraResourceType,PlanOrigin,PlanValidationState
from shared.protocol.skills import PlanValidationRequest,PlanValidationOutcome,SkillCorrelation
from skills.plan_validation import PlanValidator
from shared.protocol.ids import new_request_id, new_trace_id

def corr(): return SkillCorrelation(request_id=(rid:=new_request_id()),origin_request_id=rid,trace_id=new_trace_id())
def req(operation=NyraOperation.TURN_ON, resource=NyraResourceType.LIGHT, params=None, origin=PlanOrigin.REASONING_LLM,state=PlanValidationState.PROPOSED):
    p=ExecutionPlan(plan_id="p",origin=origin,validation_state=state,steps=[ExecutionStep(step_id="s",operation=operation,target=ExecutionTarget(reference="kitchen",resource_type=resource),parameters=params or {})])
    return PlanValidationRequest(correlation=corr(),plan=p,trusted_context={})

@pytest.mark.asyncio
async def test_valid_plan_is_materialized_without_capability_execution():
    r=await PlanValidator().validate(req())
    assert r.outcome is PlanValidationOutcome.VALIDATED
    assert r.plan.validation_state is PlanValidationState.VALIDATED

@pytest.mark.asyncio
async def test_unsupported_operation_resource_pair_is_rejected():
    r=await PlanValidator().validate(req(NyraOperation.OPEN,NyraResourceType.LIGHT))
    assert r.outcome is PlanValidationOutcome.REJECTED and r.error.code=="UNSUPPORTED_ACTION"

@pytest.mark.asyncio
async def test_unsafe_parameters_are_rejected():
    r=await PlanValidator().validate(req(params={"entity_id":"light.evil"}))
    assert r.outcome is PlanValidationOutcome.REJECTED and r.error.code=="UNSUPPORTED_PARAMETERS"
