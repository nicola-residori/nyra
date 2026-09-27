import httpx,pytest
from router.config import RouterSettings
from router.llm_client import LlmClient,LlmUnavailable
from shared.protocol.llm import LlmPurpose,LlmRequest,ReasoningContext

def test_router_llm_config(monkeypatch):
    monkeypatch.setenv("NYRA_LLM_URL","http://llm.internal:8090")
    monkeypatch.setenv("NYRA_LLM_TIMEOUT_SECONDS","9")
    s=RouterSettings.load()
    assert s.llm_url=="http://llm.internal:8090" and s.llm_timeout_seconds==9
    assert not hasattr(s,"llm_model")

@pytest.mark.asyncio
async def test_client_posts_typed_reason_request():
    async def handler(req):
        assert req.url.path=="/v1/llm/reason"
        return httpx.Response(200,json={"outcome":"COMPLETED","reasoning_id":"r1","response_text":"ok"})
    c=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client=LlmClient("http://llm",client=c)
    result=await client.reason(LlmRequest(purpose=LlmPurpose.REASONING,context=ReasoningContext(language="en",current_user_input="x",operational={"trace_id":"t"})))
    assert result.response_text=="ok"
    await c.aclose()
