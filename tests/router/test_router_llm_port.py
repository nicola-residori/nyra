import pytest
from router.router_llm_port import RouterLlmPort
from router.lifecycle.service import ContextResult
from shared.protocol.llm import ReasoningResult,ReasoningOutcome,ClarificationRequest,ReasoningError
from shared.protocol.requests import RequestStatus
from tests.router.test_request_lifecycle import request

class O:
    def __init__(self,result): self.result=result
    async def reason(self,**kwargs): return self.result

@pytest.mark.asyncio
async def test_clarification_is_router_pending_state():
    result=ReasoningResult(outcome=ReasoningOutcome.NEEDS_CLARIFICATION,reasoning_id="r",clarification=ClarificationRequest(question="Quale luce?",reason="ambiguous"))
    decision=await RouterLlmPort(O(result)).reason(request(kind="ha_assist"),ContextResult(data={},trace_id="trc"),None,None)
    assert decision.status is RequestStatus.NEEDS_CLARIFICATION
    assert decision.pending_state["llm_clarification"]["question"]=="Quale luce?"

@pytest.mark.asyncio
async def test_failed_is_terminal_and_not_reinterpreted():
    result=ReasoningResult(outcome=ReasoningOutcome.FAILED,reasoning_id="r",error=ReasoningError(code="NO_MATCH",category="reasoning"))
    decision=await RouterLlmPort(O(result)).reason(request(kind="ha_assist"),ContextResult(data={},trace_id="trc"),None,None)
    assert decision.status is RequestStatus.FAILED and decision.error=={"code":"NO_MATCH"}


@pytest.mark.asyncio
async def test_skills_plan_validation_outage_becomes_typed_router_failure():
    from router.skills_client import SkillsUnavailable
    from shared.protocol.execution import ExecutionPlan
    from shared.protocol.execution_common import ExecutionStep,ExecutionTarget,NyraOperation,NyraResourceType,PlanOrigin,PlanValidationState
    class Gate:
        async def validate_proposal(self,*args,**kwargs): raise SkillsUnavailable("offline")
    plan=ExecutionPlan(plan_id="p",origin=PlanOrigin.REASONING_LLM,validation_state=PlanValidationState.PROPOSED,steps=[ExecutionStep(step_id="s",operation=NyraOperation.TURN_ON,target=ExecutionTarget(reference="x",resource_type=NyraResourceType.LIGHT))])
    result=ReasoningResult(outcome=ReasoningOutcome.COMPLETED,reasoning_id="r",response_text="ok",proposed_execution_plan=plan)
    decision=await RouterLlmPort(O(result),action_gate=Gate(),plan_executor=object()).reason(request(kind="ha_assist"),ContextResult(data={},trace_id="trc_00000000-0000-4000-8000-000000000001"),None,None)
    assert decision.status is RequestStatus.FAILED
    assert decision.error=={"code":"SKILLS_UNAVAILABLE"}


@pytest.mark.asyncio
async def test_llm_plan_cannot_bypass_fresh_target_resolution_with_supplied_entity_id():
    from router.plan_execution import RouterPlanExecutor
    from shared.protocol.execution import ExecutionPlan
    from shared.protocol.execution_common import ExecutionStep, ExecutionTarget, ResolvedTarget, PlanOrigin, PlanValidationState, NyraOperation, NyraResourceType
    from shared.protocol.capabilities import ResolveResponse, ResolveStatus, ResolveCandidate, ResolvedResource, ExecuteResponse, CapabilityCorrelation
    from shared.protocol.common import CommonOutcome
    from shared.protocol.ids import new_trace_id
    executed = []
    class Cap:
        async def resolve(self, reference, trusted_context, *, correlation):
            assert reference.reference == "Pool pump"
            return ResolveResponse(correlation=correlation, reference=reference, status=ResolveStatus.RESOLVED, candidates=[ResolveCandidate(resource=ResolvedResource(resource_id="switch.pool", resource_type=NyraResourceType.SWITCH))])
        async def execute(self, request, trusted_context):
            executed.append(request.resource_id)
            return ExecuteResponse(correlation=request.correlation, outcome=CommonOutcome.SUCCESS)
    plan = ExecutionPlan(plan_id="p", origin=PlanOrigin.REASONING_LLM, validation_state=PlanValidationState.VALIDATED, steps=[ExecutionStep(step_id="off", operation=NyraOperation.TURN_OFF, target=ExecutionTarget(reference="Pool pump", resource_type=NyraResourceType.SWITCH, resolved=ResolvedTarget(resource_id="switch.unrelated", resource_type=NyraResourceType.SWITCH, semantic_reference="invented")))])
    await RouterPlanExecutor(Cap()).execute(plan, correlation=CapabilityCorrelation(trace_id=new_trace_id()), trusted_context={})
    assert executed == ["switch.pool"]
