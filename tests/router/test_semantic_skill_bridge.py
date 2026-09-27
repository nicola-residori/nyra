import httpx, pytest
from router.llm_client import LlmClient
from shared.protocol.llm import LlmPurpose,LlmRequest,ReasoningContext
@pytest.mark.asyncio
async def test_llm_client_posts_typed_semantic_request():
    async def handler(req):
        assert req.url.path=="/v1/llm/semantic"
        return httpx.Response(200,json={"intent":"control","actions":[{"operation":"TURN_ON","target":{"reference":"luci","kind":"LIGHT","area":"soggiorno"},"parameters":[]}],"triggers":[],"conditions":[],"confidence":{"score":0.96}})
    c=httpx.AsyncClient(transport=httpx.MockTransport(handler)); client=LlmClient("http://llm",client=c)
    result=await client.semantic(LlmRequest(purpose=LlmPurpose.SEMANTIC,context=ReasoningContext(language="it",current_user_input="Accendi le luci soggiorno")))
    assert result.actions[0].target.area=="soggiorno"; await c.aclose()
