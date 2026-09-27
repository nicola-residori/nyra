import pytest
from types import SimpleNamespace
from router.router_llm_port import RouterLlmPort
from shared.protocol.semantic import SemanticResult
class Client:
    def __init__(self): self.request=None
    async def semantic(self,request):
        self.request=request
        return SemanticResult.model_validate({"intent":"control","actions":[{"operation":"TURN_ON","target":{"reference":"luci","kind":"LIGHT","area":"soggiorno"},"parameters":[]}],"confidence":{"score":.95}})
@pytest.mark.asyncio
async def test_router_marks_semantic_as_skill_routing():
    client=Client(); port=RouterLlmPort(SimpleNamespace(llm_client=client))
    request=SimpleNamespace(language="it",input=SimpleNamespace(text="Accendi le luci soggiorno"),source=SimpleNamespace(id="speaker",area="soggiorno"))
    context=SimpleNamespace(data={},trace_id="trc_test")
    result=await port.semantic(request,context,None)
    assert result is not None
    assert client.request.context.operational["mode"]=="skill_routing"
    assert client.request.context.operational["trace_id"]=="trc_test"
