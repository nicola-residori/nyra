import pytest
from pydantic import ValidationError
from shared.protocol.execution import *
def test_operation_vocabulary_and_proposed_llm_plan():
    assert [x.value for x in NyraOperation]==["TURN_ON","TURN_OFF","OPEN","CLOSE","TOGGLE","SET","INCREASE","DECREASE","START","STOP","TRIGGER"]
    p=ExecutionPlan(plan_id="plan-1",origin=PlanOrigin.REASONING_LLM,validation_state=PlanValidationState.PROPOSED,steps=[]); assert p.validation_state is PlanValidationState.PROPOSED
def test_resolved_target_preserves_semantic_reference_and_no_native_ha_fields():
    t=ResolvedTarget(resource_id="res-1",resource_type=NyraResourceType.LIGHT,semantic_reference="lampada studio"); assert t.semantic_reference=="lampada studio"
    assert {"entity_id","service","service_data","rollback","on_failure","parallel_group"}.isdisjoint(ExecutionStep.model_fields)
def test_dependency_graph_validation():
    a=ExecutionStep(step_id="a",operation=NyraOperation.TURN_ON,target=ExecutionTarget(reference="lampada",resource_type=NyraResourceType.LIGHT))
    b=ExecutionStep(step_id="b",operation=NyraOperation.TURN_OFF,target=ExecutionTarget(reference="lampada",resource_type=NyraResourceType.LIGHT),depends_on=["a"])
    ExecutionPlan(plan_id="p",origin=PlanOrigin.SKILLS,validation_state=PlanValidationState.VALIDATED,steps=[a,b])
    with pytest.raises(ValidationError): ExecutionPlan(plan_id="p",origin=PlanOrigin.SKILLS,validation_state=PlanValidationState.VALIDATED,steps=[a,a])
