from __future__ import annotations
from uuid import uuid4
from shared.protocol.llm import CapabilityResult,CapabilityStatus,ReasoningCapability

class ReasoningCapabilityDispatcher:
    def __init__(self, memory_port=None, ha_capability=None):
        self.memory_port=memory_port
        self.ha_capability=ha_capability

    async def execute(self, capability_request, *, request, identity_user_id, context, trace_id):
        cap=capability_request.capability
        params=capability_request.parameters
        call_id=f"cap_{uuid4().hex}"
        try:
            if cap is ReasoningCapability.SEARCH_MEMORY:
                if self.memory_port is None: raise RuntimeError("MEMORY_UNAVAILABLE")
                from router.lifecycle.service import MemoryQuery
                query=params.get("query")
                if not isinstance(query,str) or not query.strip(): raise ValueError("INVALID_MEMORY_QUERY")
                data=await self.memory_port.search(request,identity_user_id,MemoryQuery(query=query),trace_id)
            elif cap is ReasoningCapability.READ_STATE:
                if self.ha_capability is None: raise RuntimeError("HA_UNAVAILABLE")
                entity=params.get("entity_id")
                if not isinstance(entity,str): raise ValueError("INVALID_ENTITY")
                data=await self.ha_capability.client.state(entity)
                if data is None: raise ValueError("RESOURCE_NOT_FOUND")
                data={"entity_id":data.get("entity_id"),"state":data.get("state")}
            elif cap is ReasoningCapability.READ_ATTRIBUTE:
                if self.ha_capability is None: raise RuntimeError("HA_UNAVAILABLE")
                entity=params.get("entity_id"); attribute=params.get("attribute")
                if not isinstance(entity,str) or not isinstance(attribute,str): raise ValueError("INVALID_ATTRIBUTE_REQUEST")
                native=await self.ha_capability.client.state(entity)
                attrs=native.get("attributes",{}) if isinstance(native,dict) else {}
                if attribute not in attrs: raise ValueError("ATTRIBUTE_NOT_FOUND")
                data={"entity_id":entity,"attribute":attribute,"value":attrs[attribute]}
            elif cap is ReasoningCapability.DISCOVER_RESOURCES:
                if self.ha_capability is None: raise RuntimeError("HA_UNAVAILABLE")
                query=str(params.get("query","")).lower()
                states=await self.ha_capability.client.states()
                items=[]
                for item in states:
                    entity=item.get("entity_id")
                    name=(item.get("attributes") or {}).get("friendly_name")
                    hay=f"{entity or ''} {name or ''}".lower()
                    if query and query not in hay: continue
                    items.append({"entity_id":entity,"name":name,"state":item.get("state")})
                    if len(items)>=20: break
                data={"items":items}
            else:
                raise ValueError("CAPABILITY_NOT_ALLOWED")
            return CapabilityResult(capability_call_id=call_id,capability=cap,status=CapabilityStatus.COMPLETED,data=data or {})
        except Exception as exc:
            return CapabilityResult(capability_call_id=call_id,capability=cap,status=CapabilityStatus.FAILED,error=str(exc) or type(exc).__name__)
