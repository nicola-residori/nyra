import pytest
from pydantic import ValidationError

from shared.protocol.execution import ExecutionPlan
from shared.protocol.execution_common import (
    ExecutionStep,
    ExecutionTarget,
    NyraOperation,
    NyraResourceType,
    PlanOrigin,
    PlanValidationState,
)
from shared.protocol.llm import (
    CapabilityRequest,
    CapabilityResult,
    CapabilityStatus,
    ClarificationRequest,
    LlmPurpose,
    LlmRequest,
    ReasoningCapability,
    ReasoningContext,
    ReasoningError,
    ReasoningOutcome,
    ReasoningResult,
    UsageMetadata,
)


def _proposed_plan(*, origin=PlanOrigin.REASONING_LLM, state=PlanValidationState.PROPOSED):
    return ExecutionPlan(
        plan_id="plan-1",
        origin=origin,
        validation_state=state,
        steps=[
            ExecutionStep(
                step_id="step-1",
                operation=NyraOperation.TURN_ON,
                target=ExecutionTarget(
                    reference="kitchen light",
                    resource_type=NyraResourceType.LIGHT,
                ),
            )
        ],
    )


def _context():
    return ReasoningContext(
        language="it",
        current_user_input="Accendi la luce se serve",
        trusted_identity={"user_id": "user-1", "display_name": "Nicola"},
        policy={"allow_actions": True},
        source="voice",
        area="kitchen",
        conversation_history=[{"role": "user", "content": "Ciao"}],
        clarification={"pending": False},
        operational={"time_of_day": "evening"},
    )


def test_llm_purpose_is_closed():
    assert {item.value for item in LlmPurpose} == {
        "SEMANTIC",
        "REASONING",
        "MEMORY_EXTRACTION",
    }
    with pytest.raises(ValidationError):
        LlmRequest(purpose="OTHER", context=_context())


def test_reasoning_outcome_is_closed():
    assert {item.value for item in ReasoningOutcome} == {
        "COMPLETED",
        "NEEDS_CAPABILITY",
        "NEEDS_CLARIFICATION",
        "FAILED",
    }


def test_reasoning_capability_allowlist_is_closed():
    assert {item.value for item in ReasoningCapability} == {
        "SEARCH_MEMORY",
        "READ_STATE",
        "READ_ATTRIBUTE",
        "DISCOVER_RESOURCES",
    }
    with pytest.raises(ValidationError):
        CapabilityRequest(capability="TURN_ON", parameters={})


def test_semantic_request_cannot_carry_reasoning_continuation():
    with pytest.raises(ValidationError):
        LlmRequest(
            purpose=LlmPurpose.SEMANTIC,
            context=_context(),
            reasoning_id="rsn-1",
        )
    with pytest.raises(ValidationError):
        LlmRequest(
            purpose=LlmPurpose.SEMANTIC,
            context=_context(),
            capability_results=[
                CapabilityResult(
                    capability_call_id="cap-1",
                    capability=ReasoningCapability.READ_STATE,
                    status=CapabilityStatus.COMPLETED,
                    data={"state": "on"},
                )
            ],
        )


def test_capability_result_requires_error_only_for_failed_status():
    with pytest.raises(ValidationError):
        CapabilityResult(
            capability_call_id="cap-1",
            capability=ReasoningCapability.READ_STATE,
            status=CapabilityStatus.FAILED,
        )
    with pytest.raises(ValidationError):
        CapabilityResult(
            capability_call_id="cap-1",
            capability=ReasoningCapability.READ_STATE,
            status=CapabilityStatus.COMPLETED,
            error="not found",
        )


def test_completed_accepts_response_and_proposed_llm_plan():
    result = ReasoningResult(
        outcome=ReasoningOutcome.COMPLETED,
        reasoning_id="rsn-1",
        response_text="Fatto.",
        proposed_execution_plan=_proposed_plan(),
        usage=UsageMetadata(input_tokens=10, output_tokens=4),
    )
    assert result.proposed_execution_plan.validation_state is PlanValidationState.PROPOSED


@pytest.mark.parametrize(
    ("origin", "state"),
    [
        (PlanOrigin.SKILLS, PlanValidationState.PROPOSED),
        (PlanOrigin.REASONING_LLM, PlanValidationState.VALIDATED),
    ],
)
def test_completed_rejects_plan_not_proposed_by_reasoning_llm(origin, state):
    with pytest.raises(ValidationError):
        ReasoningResult(
            outcome=ReasoningOutcome.COMPLETED,
            reasoning_id="rsn-1",
            proposed_execution_plan=_proposed_plan(origin=origin, state=state),
        )


def test_needs_capability_requires_exactly_capability_payload():
    request = CapabilityRequest(
        capability=ReasoningCapability.SEARCH_MEMORY,
        parameters={"query": "preferenze luci"},
        functional_reason="Need a remembered preference",
    )
    result = ReasoningResult(
        outcome=ReasoningOutcome.NEEDS_CAPABILITY,
        reasoning_id="rsn-1",
        capability_request=request,
    )
    assert result.capability_request is request

    with pytest.raises(ValidationError):
        ReasoningResult(
            outcome=ReasoningOutcome.NEEDS_CAPABILITY,
            reasoning_id="rsn-1",
        )


def test_needs_clarification_requires_clarification_payload():
    clarification = ClarificationRequest(
        question="Quale luce intendi?",
        reason="AMBIGUOUS_TARGET",
    )
    result = ReasoningResult(
        outcome=ReasoningOutcome.NEEDS_CLARIFICATION,
        reasoning_id="rsn-1",
        clarification=clarification,
    )
    assert result.clarification.question == "Quale luce intendi?"

    with pytest.raises(ValidationError):
        ReasoningResult(
            outcome=ReasoningOutcome.NEEDS_CLARIFICATION,
            reasoning_id="rsn-1",
        )


def test_failed_requires_typed_error():
    result = ReasoningResult(
        outcome=ReasoningOutcome.FAILED,
        reasoning_id="rsn-1",
        error=ReasoningError(code="UNABLE_TO_COMPLETE", category="reasoning"),
    )
    assert result.error.code == "UNABLE_TO_COMPLETE"

    with pytest.raises(ValidationError):
        ReasoningResult(
            outcome=ReasoningOutcome.FAILED,
            reasoning_id="rsn-1",
        )


@pytest.mark.parametrize(
    "result",
    [
        ReasoningResult(
            outcome=ReasoningOutcome.COMPLETED,
            reasoning_id="rsn-1",
            response_text="ok",
        ),
        ReasoningResult(
            outcome=ReasoningOutcome.NEEDS_CAPABILITY,
            reasoning_id="rsn-1",
            capability_request=CapabilityRequest(
                capability=ReasoningCapability.READ_STATE,
                parameters={"resource": "light.kitchen"},
            ),
        ),
        ReasoningResult(
            outcome=ReasoningOutcome.NEEDS_CLARIFICATION,
            reasoning_id="rsn-1",
            clarification=ClarificationRequest(question="Quale stanza?"),
        ),
        ReasoningResult(
            outcome=ReasoningOutcome.FAILED,
            reasoning_id="rsn-1",
            error=ReasoningError(code="TIMEOUT", category="technical"),
        ),
    ],
)
def test_outcome_rejects_payloads_owned_by_other_outcomes(result):
    payload = result.model_dump()
    if result.outcome is not ReasoningOutcome.NEEDS_CAPABILITY:
        payload["capability_request"] = {
            "capability": "READ_STATE",
            "parameters": {},
        }
    elif result.outcome is not ReasoningOutcome.NEEDS_CLARIFICATION:
        payload["clarification"] = {"question": "extra"}
    with pytest.raises(ValidationError):
        ReasoningResult.model_validate(payload)


def test_protocol_models_forbid_unknown_fields():
    with pytest.raises(ValidationError):
        ReasoningContext(
            language="it",
            current_user_input="ciao",
            provider="openai",
        )
