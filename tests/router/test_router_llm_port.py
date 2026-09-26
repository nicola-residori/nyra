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
