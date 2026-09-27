from __future__ import annotations
from shared.protocol.llm import ReasoningContext

_ALLOWED_OPERATIONAL={"mode","timezone","locale"}

def build_reasoning_context(request, context, pending_state=None)->ReasoningContext:
    data=context.data if isinstance(context.data,dict) else {}
    identity=data.get("identity")
    trusted=None
    if isinstance(identity,dict):
        trusted={k:identity[k] for k in ("user_id","display_name","resolution_source") if k in identity}
    policy=data.get("policy") if isinstance(data.get("policy"),dict) else {}
    operational={k:data[k] for k in _ALLOWED_OPERATIONAL if k in data}
    if context.trace_id:
        operational["trace_id"]=context.trace_id
    request_id=getattr(request,"request_id",None)
    if request_id:
        operational["request_id"]=request_id
        operational["origin_request_id"]=getattr(request,"origin_request_id",None) or request_id
    clarification=None
    if isinstance(pending_state,dict):
        item=pending_state.get("llm_clarification")
        clarification=item if isinstance(item,dict) else None
    return ReasoningContext(
        language=request.language,current_user_input=request.input.text,
        trusted_identity=trusted,policy=policy,
        source=request.source.id if request.source else None,
        area=request.source.area if request.source else None,
        conversation_history=[],clarification=clarification,operational=operational,
    )
