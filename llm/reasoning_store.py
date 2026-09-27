from __future__ import annotations
from dataclasses import dataclass
from uuid import uuid4

class ReasoningStateError(ValueError):
    pass

@dataclass(frozen=True)
class ReasoningState:
    reasoning_id: str
    trace_id: str

class ReasoningStore:
    def __init__(self):
        self._states: dict[str,ReasoningState]={}

    def create(self,trace_id:str)->str:
        reasoning_id=str(uuid4())
        self._states[reasoning_id]=ReasoningState(reasoning_id,trace_id)
        return reasoning_id

    def require(self,reasoning_id:str,trace_id:str)->ReasoningState:
        state=self._states.get(reasoning_id)
        if state is None or state.trace_id != trace_id:
            raise ReasoningStateError("reasoning_id is missing or belongs to another trace")
        return state

    def complete(self,reasoning_id:str)->None:
        self._states.pop(reasoning_id,None)
