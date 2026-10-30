import json
import pytest
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


@pytest.mark.asyncio
async def test_verified_already_done_command_has_an_explicit_noop_plan():
    from shared.protocol.execution import ExecutionPlan
    request = LlmRequest(purpose=LlmPurpose.REASONING, context=ReasoningContext(language="it", current_user_input="spegni la pompa già spenta"))
    payload = json.loads(reasoning_messages(request)[0]["content"])
    plan = ExecutionPlan.model_validate(payload["action_plan_contract"]["noop_example"])
    assert plan.steps == []
    from router.router_llm_port import RouterLlmPort
    from router.llm_action_gate import LlmActionGate
    from router.plan_execution import RouterPlanExecutor
    from router.lifecycle.service import ContextResult
    from skills.plan_validation import PlanValidator
    from shared.protocol.skills import PlanValidationRequest
    from shared.protocol.llm import ReasoningResult, ReasoningOutcome
    from shared.protocol.requests import RequestStatus
    from shared.protocol.ids import new_trace_id
    from tests.router.test_request_lifecycle import request as user_request
    class Model:
        async def reason(self, **kwargs):
            return ReasoningResult(outcome=ReasoningOutcome.COMPLETED, reasoning_id="r", response_text="Già spenta.", proposed_execution_plan=plan)
    class Skills:
        async def validate_plan(self, plan, *, correlation, trusted_context):
            return await PlanValidator().validate(PlanValidationRequest(correlation=correlation, plan=plan, trusted_context=trusted_context))
    decision = await RouterLlmPort(Model(), action_gate=LlmActionGate(Skills()), plan_executor=RouterPlanExecutor(object())).reason(user_request(kind="ha_assist"), ContextResult(data={}, trace_id=new_trace_id()), None, None)
    assert decision.status is RequestStatus.COMPLETED
    assert not decision.continue_conversation
