import pytest
from shared.protocol.capabilities import CapabilityCorrelation,ExecuteRequest
from shared.protocol.common import CommonOutcome
from shared.protocol.execution_common import NyraOperation,NyraResourceType
from router.ha_capability import HomeAssistantCapabilityPort
class Client:
 def __init__(self): self.calls=[]
 async def state(self,entity_id): return {"entity_id":entity_id,"state":"on","attributes":{"friendly_name":"Routine irrigazione"}}
 async def invoke(self,domain,service,entity_id,parameters): self.calls.append((domain,service,entity_id,parameters))
@pytest.mark.asyncio
async def test_router_can_trigger_existing_home_assistant_automation():
 client=Client(); port=HomeAssistantCapabilityPort(client); c=CapabilityCorrelation(request_id="req_00000000-0000-4000-8000-000000000001",origin_request_id="req_00000000-0000-4000-8000-000000000001",trace_id="trc_00000000-0000-4000-8000-000000000001")
 response=await port.execute(ExecuteRequest(correlation=c,operation=NyraOperation.TRIGGER,resource_id="automation.routine_irrigazione",resource_type=NyraResourceType.AUTOMATION),{})
 assert response.outcome is CommonOutcome.SUCCESS and client.calls==[("automation","trigger","automation.routine_irrigazione",{})]
