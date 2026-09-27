import pytest
from pydantic import ValidationError
from shared.protocol.execution import ExecutionPlan
from shared.protocol.execution_common import ExecutionStep,ExecutionTarget,NyraOperation,NyraResourceType,PlanOrigin,PlanValidationState
from shared.protocol.skills import PlanValidationRequest,PlanValidationResponse,PlanValidationOutcome,SkillCorrelation
from shared.protocol.ids import new_request_id, new_trace_id

def plan(state=PlanValidationState.PROPOSED, origin=PlanOrigin.REASONING_LLM):
    return ExecutionPlan(plan_id="p1",origin=origin,validation_state=state,steps=[
        ExecutionStep(step_id="s1",operation=NyraOperation.TURN_ON,target=ExecutionTarget(reference="kitchen light",resource_type=NyraResourceType.LIGHT))
    ])

def corr():
    return SkillCorrelation(request_id=(rid:=new_request_id()),origin_request_id=rid,trace_id=new_trace_id())

def test_contract_accepts_proposed_and_validated_output():
    req=PlanValidationRequest(correlation=corr(),plan=plan(),trusted_context={"allowed_resource_ids":["light.kitchen"]})
    assert req.plan.validation_state is PlanValidationState.PROPOSED
    validated=plan(PlanValidationState.VALIDATED)
    res=PlanValidationResponse(correlation=corr(),outcome=PlanValidationOutcome.VALIDATED,plan=validated)
    assert res.plan.validation_state is PlanValidationState.VALIDATED

def test_contract_rejects_invalid_state_shapes():
    with pytest.raises(ValidationError):
        PlanValidationRequest(correlation=corr(),plan=plan(PlanValidationState.VALIDATED),trusted_context={})
    with pytest.raises(ValidationError):
        PlanValidationResponse(correlation=corr(),outcome=PlanValidationOutcome.VALIDATED,plan=plan())
