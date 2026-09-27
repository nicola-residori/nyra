import pytest
from router.reasoning_orchestrator import ReasoningOrchestrator,ReasoningBudgetExceeded
from router.lifecycle.service import ContextResult
from shared.protocol.llm import ReasoningResult,ReasoningOutcome,CapabilityRequest,ReasoningCapability,CapabilityResult,CapabilityStatus
from tests.router.test_request_lifecycle import request

class LLM:
    def __init__(self,results): self.results=list(results); self.calls=[]
    async def reason(self,r): self.calls.append(r); return self.results.pop(0)
class Dispatcher:
    async def execute(self,*a,**k): return CapabilityResult(capability_call_id="c1",capability=ReasoningCapability.READ_STATE,status=CapabilityStatus.COMPLETED,data={"state":"on"})

@pytest.mark.asyncio
async def test_capability_result_continues_same_reasoning():
    llm=LLM([
      ReasoningResult(outcome=ReasoningOutcome.NEEDS_CAPABILITY,reasoning_id="r1",capability_request=CapabilityRequest(capability=ReasoningCapability.READ_STATE,parameters={"entity_id":"light.x"})),
      ReasoningResult(outcome=ReasoningOutcome.COMPLETED,reasoning_id="r1",response_text="done")])
    result=await ReasoningOrchestrator(llm,Dispatcher()).reason(request=request(kind="ha_assist"),context=ContextResult(data={},trace_id="trc"),pending_state=None,identity_user_id="u")
    assert result.response_text=="done" and llm.calls[1].reasoning_id=="r1" and len(llm.calls[1].capability_results)==1

@pytest.mark.asyncio
async def test_round_budget_is_router_owned():
    item=ReasoningResult(outcome=ReasoningOutcome.NEEDS_CAPABILITY,reasoning_id="r1",capability_request=CapabilityRequest(capability=ReasoningCapability.READ_STATE,parameters={"entity_id":"light.x"}))
    with pytest.raises(ReasoningBudgetExceeded):
      await ReasoningOrchestrator(LLM([item,item,item]),Dispatcher(),max_rounds=3).reason(request=request(kind="ha_assist"),context=ContextResult(data={},trace_id="trc"),pending_state=None,identity_user_id="u")
