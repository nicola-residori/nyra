from types import SimpleNamespace
from llm.observability import LlmDiagnostics
from shared.protocol.ids import new_request_id,new_trace_id
def test_llm_trace_is_correlated_and_safe():
 r=[];d=LlmDiagnostics(sink=SimpleNamespace(emit_record=r.append));q=new_request_id();t=new_trace_id();d.trace(purpose="SEMANTIC",outcome="SUCCESS",trace_id=t,request_id=q,origin_request_id=q,latency_ms=12.3);x=r[0];assert x.ct=="LLM" and x.trace_id==t and x.request_id==q and x.span_elapsed_ms==12.3
