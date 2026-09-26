from __future__ import annotations
from dataclasses import dataclass,asdict

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
    def __init__(self): self._items=[]
    def record(self,**kwargs): self._items.append(LlmDiagnostic(**kwargs))
    def items(self): return [asdict(x) for x in self._items]
