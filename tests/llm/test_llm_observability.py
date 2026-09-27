from llm.observability import LlmDiagnostics

def test_privacy_safe_metadata_excludes_sensitive_content():
    d=LlmDiagnostics()
    d.record(purpose="REASONING",outcome="COMPLETED",provider="openai",model="gpt-x",attempt=1,fallback=False,latency_ms=12.5,input_tokens=10,output_tokens=4,valid=True,error_code=None,cost=None)
    item=d.items()[0]
    assert item["purpose"]=="REASONING"
    assert item["cost"] is None
    forbidden={"prompt","messages","history","memory","chain_of_thought","content"}
    assert forbidden.isdisjoint(item)
import pytest
from llm.config import ModelTarget
from llm.provider_service import ProviderService
from llm.providers.base import ProviderAdapter,ProviderError,ProviderErrorKind,ProviderRequest,ProviderResponse,ProviderUsage

class ObsAdapter(ProviderAdapter):
    def __init__(self,items): self.items=list(items)
    async def infer(self,request):
        x=self.items.pop(0)
        if isinstance(x,Exception): raise x
        return x

def obs_req():
    return ProviderRequest(purpose="SEMANTIC",model="ignored",messages=({"role":"user","content":"PRIVATE-CONTENT"},),response_schema={})

@pytest.mark.asyncio
async def test_live_success_diagnostic_is_privacy_safe():
    d=LlmDiagnostics()
    s=ProviderService(ObsAdapter([ProviderResponse("{}","openai","semantic",ProviderUsage(12,3))]),ModelTarget("openai","default"),None,purpose_targets={"SEMANTIC":ModelTarget("openai","semantic")},diagnostics=d)
    await s.infer(obs_req())
    x=d.items()[0]
    assert (x["purpose"],x["outcome"],x["provider"],x["model"])==("SEMANTIC","SUCCESS","openai","semantic")
    assert (x["attempt"],x["fallback"],x["input_tokens"],x["output_tokens"],x["valid"])==(1,False,12,3,True)
    assert isinstance(x["latency_ms"],float)
    assert "PRIVATE-CONTENT" not in repr(x)

@pytest.mark.asyncio
async def test_live_fallback_records_both_attempts():
    d=LlmDiagnostics()
    err=ProviderError(ProviderErrorKind.TIMEOUT,"openai","semantic","timeout",True)
    s=ProviderService(ObsAdapter([err,ProviderResponse("{}","anthropic","fallback")]),ModelTarget("openai","default"),ModelTarget("anthropic","fallback"),purpose_targets={"SEMANTIC":ModelTarget("openai","semantic")},diagnostics=d)
    await s.infer(obs_req())
    xs=d.items()
    assert [(x["outcome"],x["attempt"],x["fallback"]) for x in xs]==[("ERROR",1,False),("SUCCESS",2,True)]
    assert xs[0]["error_code"]=="TIMEOUT"
