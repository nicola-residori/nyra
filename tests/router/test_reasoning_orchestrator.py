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


@pytest.mark.asyncio
async def test_later_reasoning_keeps_discovery_and_subsequent_measurement_results():
    discovery = CapabilityResult(capability_call_id="discover", capability=ReasoningCapability.DISCOVER_RESOURCES, status=CapabilityStatus.COMPLETED, data={"items": [{"entity_id": "sensor.solar", "state": "1.2", "unit_of_measurement": "kW"}]})
    reading = CapabilityResult(capability_call_id="read", capability=ReasoningCapability.READ_STATE, status=CapabilityStatus.COMPLETED, data={"entity_id": "sensor.solar", "state": "1.3"})
    class Data:
        async def execute(self, cap, **kwargs):
            return discovery if cap.capability is ReasoningCapability.DISCOVER_RESOURCES else reading
    llm = LLM([
        ReasoningResult(outcome=ReasoningOutcome.NEEDS_CAPABILITY, reasoning_id="r", capability_request=CapabilityRequest(capability=ReasoningCapability.DISCOVER_RESOURCES, parameters={"query": "solar"})),
        ReasoningResult(outcome=ReasoningOutcome.NEEDS_CAPABILITY, reasoning_id="r", capability_request=CapabilityRequest(capability=ReasoningCapability.READ_STATE, parameters={"entity_id": "sensor.solar"})),
        ReasoningResult(outcome=ReasoningOutcome.COMPLETED, reasoning_id="r", response_text="1.3 kW"),
    ])
    await ReasoningOrchestrator(llm, Data()).reason(request=request(kind="ha_assist"), context=ContextResult(data={}, trace_id="trace"), pending_state=None, identity_user_id=None)
    assert [item.capability_call_id for item in llm.calls[2].capability_results] == ["discover", "read"]


@pytest.mark.asyncio
async def test_provider_knows_when_it_must_answer_or_clarify_without_more_tools():
    tool = ReasoningResult(outcome=ReasoningOutcome.NEEDS_CAPABILITY, reasoning_id="r", capability_request=CapabilityRequest(capability=ReasoningCapability.DISCOVER_RESOURCES, parameters={"query": "missing"}))
    from shared.protocol.llm import ClarificationRequest
    llm = LLM([tool, tool, ReasoningResult(outcome=ReasoningOutcome.NEEDS_CLARIFICATION, reasoning_id="r", clarification=ClarificationRequest(question="Quale impianto?"))])
    await ReasoningOrchestrator(llm, Dispatcher(), max_rounds=3).reason(request=request(kind="ha_assist"), context=ContextResult(data={}, trace_id="trace"), pending_state=None, identity_user_id=None)
    assert [call.context.operational["remaining_capability_calls"] for call in llm.calls] == [2, 1, 0]
