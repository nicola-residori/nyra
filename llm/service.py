from __future__ import annotations
import json
from pydantic import ValidationError
from llm.providers.base import ProviderRequest
from llm.reasoning_store import ReasoningStore
from llm.prompts import semantic_messages, reasoning_messages
from shared.protocol.llm import LlmPurpose,LlmRequest,ReasoningOutcome,ReasoningResult,UsageMetadata
from shared.protocol.semantic import SemanticResult

class LlmService:
    def __init__(self,provider,store:ReasoningStore|None=None):
        self.provider=provider
        self.store=store or ReasoningStore()

    async def semantic(self,request:LlmRequest)->SemanticResult:
        if request.purpose is not LlmPurpose.SEMANTIC:
            raise ValueError("semantic endpoint requires SEMANTIC purpose")
        response=await self.provider.infer(ProviderRequest(
            purpose=request.purpose.value,model="service-owned",
            messages=semantic_messages(request),response_schema=SemanticResult.model_json_schema(),
        ))
        return SemanticResult.model_validate(json.loads(response.content))

    async def reason(self,request:LlmRequest)->ReasoningResult:
        if request.purpose is not LlmPurpose.REASONING:
            raise ValueError("reason endpoint requires REASONING purpose")
        trace_id=request.context.operational.get("trace_id")
        if not isinstance(trace_id,str) or not trace_id:
            raise ValueError("reasoning requires operational.trace_id")
        reasoning_id=request.reasoning_id
        if reasoning_id is None:
            reasoning_id=self.store.create(trace_id)
        else:
            self.store.require(reasoning_id,trace_id)
        response=await self.provider.infer(ProviderRequest(
            purpose=request.purpose.value,model="service-owned",
            messages=reasoning_messages(request),response_schema=ReasoningResult.model_json_schema(),
        ))
        raw=json.loads(response.content)
        raw["reasoning_id"]=reasoning_id
        usage=getattr(response,"usage",None)
        if usage is not None:
            raw["usage"]={"input_tokens":usage.input_tokens,"output_tokens":usage.output_tokens}
        try:
            result=ReasoningResult.model_validate(raw)
        except Exception:
            self.store.complete(reasoning_id)
            raise
        if result.outcome in {ReasoningOutcome.COMPLETED,ReasoningOutcome.NEEDS_CLARIFICATION,ReasoningOutcome.FAILED}:
            self.store.complete(reasoning_id)
        return result
