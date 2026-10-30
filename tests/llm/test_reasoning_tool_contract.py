import json
from llm.prompts import reasoning_messages
from shared.protocol.llm import LlmPurpose, LlmRequest, ReasoningContext


def test_provider_receives_supported_read_tool_parameter_contract():
    request = LlmRequest(purpose=LlmPurpose.REASONING, context=ReasoningContext(language="it", current_user_input="resoconto fotovoltaico"))
    payload = json.loads(reasoning_messages(request)[0]["content"])
    assert set(payload["read_tools"]) == {"DISCOVER_RESOURCES", "READ_STATE", "READ_ATTRIBUTE", "SEARCH_MEMORY"}
    assert set(payload["read_tools"]["DISCOVER_RESOURCES"]["parameters"]) == {"query"}
    assert set(payload["read_tools"]["READ_ATTRIBUTE"]["parameters"]) == {"entity_id", "attribute"}


def test_action_request_exposes_a_proposed_plan_contract_alongside_read_tools():
    from shared.protocol.execution import ExecutionPlan
    from shared.protocol.execution_common import PlanOrigin, PlanValidationState, NyraOperation
    request = LlmRequest(purpose=LlmPurpose.REASONING, context=ReasoningContext(language="it", current_user_input="se la pompa è accesa spegnila"))
    payload = json.loads(reasoning_messages(request)[0]["content"])
    example = ExecutionPlan.model_validate(payload["action_plan_contract"]["example"])
    assert example.origin is PlanOrigin.REASONING_LLM
    assert example.validation_state is PlanValidationState.PROPOSED
    assert example.steps[0].operation is NyraOperation.TURN_OFF
    assert example.steps[0].target.resolved is None
