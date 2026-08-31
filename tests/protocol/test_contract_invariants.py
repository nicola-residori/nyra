from shared.protocol.capabilities import CapabilityCorrelation, ExecuteRequest, is_idempotent_operation
from shared.protocol.execution import ExecutionPlan, NyraOperation, PlanOrigin, PlanValidationState
from shared.protocol.ids import CorrelationContext
from shared.protocol.semantic import SemanticResult, SemanticTarget


def test_shared_correlation_never_requires_session_id():
    assert "session_id" not in CorrelationContext.model_fields
    assert "session_id" not in CapabilityCorrelation.model_fields


def test_capability_contracts_have_no_auth_caller_or_raw_ha_service_fields():
    forbidden = {"authorization", "token", "caller", "roles", "service"}
    assert forbidden.isdisjoint(CapabilityCorrelation.model_fields)
    assert forbidden.isdisjoint(ExecuteRequest.model_fields)


def test_semantic_result_cannot_embed_resolved_ha_resource():
    assert {"resource_id", "entity_id"}.isdisjoint(SemanticTarget.model_fields)
    assert {"authorization", "entity_id", "service_data", "execution_plan"}.isdisjoint(SemanticResult.model_fields)


def test_llm_plan_can_remain_proposed_and_untrusted():
    plan = ExecutionPlan(plan_id="p", origin=PlanOrigin.REASONING_LLM, validation_state=PlanValidationState.PROPOSED, steps=[])
    assert plan.validation_state is PlanValidationState.PROPOSED


def test_protocol_has_no_manual_authentication_abstraction():
    forbidden = {"authorization", "token", "roles", "caller", "credentials"}
    for model in (CorrelationContext, CapabilityCorrelation, ExecuteRequest, SemanticResult):
        assert forbidden.isdisjoint(model.model_fields)


def test_non_idempotent_operations_are_not_retry_safe():
    for operation in (NyraOperation.TOGGLE, NyraOperation.INCREASE, NyraOperation.DECREASE, NyraOperation.TRIGGER):
        assert not is_idempotent_operation(operation)
