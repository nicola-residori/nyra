import pytest
from types import SimpleNamespace
from router.reasoning_capabilities import ReasoningCapabilityDispatcher
from shared.protocol.llm import CapabilityRequest,ReasoningCapability,CapabilityStatus
from tests.router.test_request_lifecycle import request,ContextResult

class Memory:
    def __init__(self): self.calls=[]
    async def search(self,request,user,query,trace): self.calls.append((user,query.query,trace)); return {"items":[{"text":"x"}]}
class Client:
    async def state(self,e): return {"entity_id":e,"state":"on","attributes":{"brightness":10}}
    async def states(self): return [{"entity_id":"light.kitchen","state":"on","attributes":{"friendly_name":"Kitchen"}}]
class HA:
    client=Client()

@pytest.mark.asyncio
@pytest.mark.parametrize("cap,params",[
 (ReasoningCapability.SEARCH_MEMORY,{"query":"coffee"}),
 (ReasoningCapability.READ_STATE,{"entity_id":"light.kitchen"}),
 (ReasoningCapability.READ_ATTRIBUTE,{"entity_id":"light.kitchen","attribute":"brightness"}),
 (ReasoningCapability.DISCOVER_RESOURCES,{"query":"kitchen"}),
])
async def test_only_four_read_capabilities_execute(cap,params):
    d=ReasoningCapabilityDispatcher(Memory(),HA())
    result=await d.execute(CapabilityRequest(capability=cap,parameters=params),request=request(kind="ha_assist"),identity_user_id="u",context=ContextResult(data={},trace_id="trc"),trace_id="trc")
    assert result.status is CapabilityStatus.COMPLETED
