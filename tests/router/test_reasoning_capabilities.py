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
    async def reasoning_read_state(self,e,trusted_context,*,correlation):
        data=await self.client.state(e)
        if data is None: raise ValueError("RESOURCE_NOT_FOUND")
        return {"entity_id":data.get("entity_id"),"state":data.get("state")}
    async def reasoning_read_attribute(self,e,a,trusted_context,*,correlation):
        data=await self.client.state(e); attrs=data.get("attributes",{}) if data else {}
        if a not in attrs: raise ValueError("ATTRIBUTE_NOT_FOUND")
        return {"entity_id":e,"attribute":a,"value":attrs[a]}
    async def reasoning_discover_resources(self,q,trusted_context,*,correlation):
        items=[]
        for item in await self.client.states():
            name=(item.get("attributes") or {}).get("friendly_name")
            if q.lower() in f"{item.get('entity_id','')} {name or ''}".lower():
                items.append({"entity_id":item.get("entity_id"),"name":name,"state":item.get("state")})
        return {"items":items}

@pytest.mark.asyncio
@pytest.mark.parametrize("cap,params",[
 (ReasoningCapability.SEARCH_MEMORY,{"query":"coffee"}),
 (ReasoningCapability.READ_STATE,{"entity_id":"light.kitchen"}),
 (ReasoningCapability.READ_ATTRIBUTE,{"entity_id":"light.kitchen","attribute":"brightness"}),
 (ReasoningCapability.DISCOVER_RESOURCES,{"query":"kitchen"}),
])
async def test_only_four_read_capabilities_execute(cap,params):
    d=ReasoningCapabilityDispatcher(Memory(),HA())
    result=await d.execute(CapabilityRequest(capability=cap,parameters=params),request=request(kind="ha_assist"),identity_user_id="u",context=ContextResult(data={},trace_id="trc_00000000-0000-4000-8000-000000000001"),trace_id="trc_00000000-0000-4000-8000-000000000001")
    assert result.status is CapabilityStatus.COMPLETED

class PolicyAwareHA:
    def __init__(self): self.calls=[]
    async def reasoning_read_state(self, entity, trusted_context, *, correlation):
        self.calls.append(("state",entity,trusted_context,correlation))
        allowed=trusted_context.get("allowed_resource_ids")
        if isinstance(allowed,list) and entity not in allowed: raise ValueError("RESOURCE_DENIED")
        return {"entity_id":entity,"state":"on"}
    async def reasoning_read_attribute(self, entity, attribute, trusted_context, *, correlation):
        self.calls.append(("attribute",entity,attribute,trusted_context,correlation))
        allowed=trusted_context.get("allowed_resource_ids")
        if isinstance(allowed,list) and entity not in allowed: raise ValueError("RESOURCE_DENIED")
        return {"entity_id":entity,"attribute":attribute,"value":10}
    async def reasoning_discover_resources(self, query, trusted_context, *, correlation):
        self.calls.append(("discover",query,trusted_context,correlation))
        return {"items":[{"entity_id":x,"name":x,"state":"on"} for x in trusted_context.get("allowed_resource_ids",[])]}

@pytest.mark.asyncio
async def test_reasoning_ha_reads_use_policy_aware_correlated_port():
    ha=PolicyAwareHA(); d=ReasoningCapabilityDispatcher(Memory(),ha)
    req=request(kind="ha_assist")
    ctx=ContextResult(data={"allowed_resource_ids":["light.kitchen"]},trace_id="trc_00000000-0000-4000-8000-000000000001")
    ok=await d.execute(CapabilityRequest(capability=ReasoningCapability.READ_STATE,parameters={"entity_id":"light.kitchen"}),request=req,identity_user_id="u",context=ctx,trace_id=ctx.trace_id)
    denied=await d.execute(CapabilityRequest(capability=ReasoningCapability.READ_STATE,parameters={"entity_id":"light.private"}),request=req,identity_user_id="u",context=ctx,trace_id=ctx.trace_id)
    assert ok.status is CapabilityStatus.COMPLETED
    assert denied.status is CapabilityStatus.FAILED
    assert denied.error == "RESOURCE_DENIED"
    correlation=ha.calls[0][-1]
    assert correlation.request_id == req.request_id
    assert correlation.trace_id == ctx.trace_id

@pytest.mark.asyncio
async def test_reasoning_discovery_is_policy_scoped():
    ha=PolicyAwareHA(); d=ReasoningCapabilityDispatcher(Memory(),ha)
    req=request(kind="ha_assist")
    ctx=ContextResult(data={"allowed_resource_ids":["light.kitchen"]},trace_id="trc_00000000-0000-4000-8000-000000000001")
    result=await d.execute(CapabilityRequest(capability=ReasoningCapability.DISCOVER_RESOURCES,parameters={"query":"light"}),request=req,identity_user_id="u",context=ctx,trace_id=ctx.trace_id)
    assert result.status is CapabilityStatus.COMPLETED
    assert result.data["items"] == [{"entity_id":"light.kitchen","name":"light.kitchen","state":"on"}]
