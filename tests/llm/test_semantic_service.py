import json
import pytest
from llm.service import LlmService
from llm.providers.base import ProviderResponse
from shared.protocol.llm import LlmPurpose, LlmRequest, ReasoningContext

class Provider:
    def __init__(self,payload): self.payload=payload; self.requests=[]
    async def infer(self,request):
        self.requests.append(request)
        return ProviderResponse(json.dumps(self.payload),"fake","model")

@pytest.mark.asyncio
async def test_semantic_is_stateless_typed_and_language_bound():
    provider=Provider({"intent":"query","domain":"home","actions":[],"triggers":[],"conditions":[]})
    service=LlmService(provider)
    req=LlmRequest(purpose=LlmPurpose.SEMANTIC,context=ReasoningContext(language="it",current_user_input="come sta casa?"))
    result=await service.semantic(req)
    assert result.intent=="query"
    assert len(provider.requests)==1
    message=provider.requests[0].messages[0]["content"]
    assert '"language":"it"' in message
    assert "chain-of-thought" not in message.lower()
