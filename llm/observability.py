from __future__ import annotations
from dataclasses import dataclass,asdict
from collections import deque
from shared.protocol.ids import new_span_id
from shared.protocol.observability import LogKind,LogLevel,LogRecord

@dataclass
class LlmDiagnostic:
    purpose:str
    outcome:str
    provider:str|None=None
    model:str|None=None
    attempt:int=1
    fallback:bool=False
    latency_ms:float|None=None
    input_tokens:int|None=None
    output_tokens:int|None=None
    valid:bool|None=None
    error_code:str|None=None
    cost:float|None=None

class LlmDiagnostics:
    def __init__(self, max_items: int = 200, sink=None):
        self._items=deque(maxlen=max(1,int(max_items)))
        self._sink=sink
    def record(self,**kwargs): self._items.append(LlmDiagnostic(**kwargs))
    def trace(self, *, purpose, outcome, trace_id, request_id=None, origin_request_id=None, latency_ms=None, fault=False):
        if self._sink is None or not trace_id: return
        self._sink.emit_record(LogRecord(ct="LLM",level=LogLevel.ERROR if fault else LogLevel.INFO,kind=LogKind.FAULT if fault else LogKind.EVENT,event=f"llm.{purpose.lower()}",request_id=request_id,origin_request_id=origin_request_id,trace_id=trace_id,span_id=new_span_id("LLM",purpose.lower()),operation=f"llm.{purpose.lower()}",result=outcome,span_elapsed_ms=latency_ms,params={}))
    def items(self): return [asdict(x) for x in self._items]
