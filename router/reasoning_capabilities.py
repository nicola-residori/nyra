from __future__ import annotations
from uuid import uuid4
from shared.protocol.capabilities import CapabilityCorrelation
from shared.protocol.llm import CapabilityResult,CapabilityStatus,ReasoningCapability

class ReasoningCapabilityDispatcher:
    def __init__(self, memory_port=None, ha_capability=None):
        self.memory_port=memory_port; self.ha_capability=ha_capability

    @staticmethod
    def _correlation(request, trace_id):
        return CapabilityCorrelation(request_id=request.request_id,origin_request_id=request.origin_request_id or request.request_id,trace_id=trace_id)

    async def execute(self, capability_request, *, request, identity_user_id, context, trace_id):
        cap=capability_request.capability; params=capability_request.parameters
        call_id=f"cap_{uuid4().hex}"
        trusted=context.data if isinstance(context.data,dict) else {}
        correlation=self._correlation(request,trace_id)
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
                data=await self.ha_capability.reasoning_read_state(entity,trusted,correlation=correlation)
            elif cap is ReasoningCapability.READ_ATTRIBUTE:
                if self.ha_capability is None: raise RuntimeError("HA_UNAVAILABLE")
                entity=params.get("entity_id"); attribute=params.get("attribute")
                if not isinstance(entity,str) or not isinstance(attribute,str): raise ValueError("INVALID_ATTRIBUTE_REQUEST")
                data=await self.ha_capability.reasoning_read_attribute(entity,attribute,trusted,correlation=correlation)
            elif cap is ReasoningCapability.DISCOVER_RESOURCES:
                if self.ha_capability is None: raise RuntimeError("HA_UNAVAILABLE")
                data=await self.ha_capability.reasoning_discover_resources(str(params.get("query","")),trusted,correlation=correlation)
            else: raise ValueError("CAPABILITY_NOT_ALLOWED")
            return CapabilityResult(capability_call_id=call_id,capability=cap,status=CapabilityStatus.COMPLETED,data=data or {})
        except Exception as exc:
            return CapabilityResult(capability_call_id=call_id,capability=cap,status=CapabilityStatus.FAILED,error=str(exc) or type(exc).__name__)
