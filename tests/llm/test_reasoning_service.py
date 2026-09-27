import json
import pytest
from llm.service import LlmService
from llm.reasoning_store import ReasoningStateError
from llm.providers.base import ProviderResponse
from shared.protocol.llm import LlmPurpose,LlmRequest,ReasoningContext,ReasoningOutcome

class Provider:
    def __init__(self,payloads): self.payloads=list(payloads); self.requests=[]
    async def infer(self,request):
        self.requests.append(request)
        return ProviderResponse(json.dumps(self.payloads.pop(0)),"fake","model")

def req(trace, reasoning_id=None, capability_results=None):
    return LlmRequest(
        purpose=LlmPurpose.REASONING,
        reasoning_id=reasoning_id,
        capability_results=capability_results or [],
        context=ReasoningContext(
            language="en",
            current_user_input="help",
            operational={"trace_id":trace},
        ),
    )

@pytest.mark.asyncio
@pytest.mark.parametrize("payload,outcome",[
    ({"outcome":"COMPLETED","reasoning_id":"ignored","response_text":"done"},"COMPLETED"),
    ({"outcome":"NEEDS_CAPABILITY","reasoning_id":"ignored","capability_request":{"capability":"READ_STATE","parameters":{"entity":"light.kitchen"}}},"NEEDS_CAPABILITY"),
    ({"outcome":"NEEDS_CLARIFICATION","reasoning_id":"ignored","clarification":{"question":"Which light?"}},"NEEDS_CLARIFICATION"),
    ({"outcome":"FAILED","reasoning_id":"ignored","error":{"code":"NOPE","category":"reasoning"}},"FAILED"),
])
async def test_four_reasoning_outcomes_are_typed(payload,outcome):
    service=LlmService(Provider([payload]))
    result=await service.reason(req("trace-a"))
    assert result.outcome.value==outcome
    assert result.reasoning_id!="ignored"

@pytest.mark.asyncio
async def test_continue_same_reasoning_id_and_cross_trace_rejected():
    provider=Provider([
        {"outcome":"NEEDS_CAPABILITY","reasoning_id":"x","capability_request":{"capability":"READ_STATE","parameters":{}}},
        {"outcome":"COMPLETED","reasoning_id":"x","response_text":"done"},
    ])
    service=LlmService(provider)
    first=await service.reason(req("trace-a"))
    second=await service.reason(req("trace-a",first.reasoning_id))
    assert second.reasoning_id==first.reasoning_id
    with pytest.raises(ReasoningStateError):
        await service.reason(req("trace-b",first.reasoning_id))

@pytest.mark.asyncio
async def test_terminal_result_cleans_store():
    service=LlmService(Provider([{"outcome":"COMPLETED","reasoning_id":"x","response_text":"done"}]))
    result=await service.reason(req("trace-a"))
    with pytest.raises(ReasoningStateError):
        service.store.require(result.reasoning_id,"trace-a")

@pytest.mark.asyncio
async def test_memory_extraction_is_not_operational():
    service=LlmService(Provider([]))
    request=LlmRequest(purpose=LlmPurpose.MEMORY_EXTRACTION,context=ReasoningContext(language="en",current_user_input="x"))
    with pytest.raises(ValueError):
        await service.reason(request)
