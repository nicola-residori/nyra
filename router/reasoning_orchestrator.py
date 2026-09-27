from __future__ import annotations
import asyncio
from shared.protocol.llm import LlmPurpose,LlmRequest,ReasoningOutcome
from router.reasoning_context import build_reasoning_context

class ReasoningBudgetExceeded(RuntimeError):
    pass

class ReasoningOrchestrator:
    def __init__(self,llm_client,dispatcher,max_rounds:int=3,total_timeout_seconds:float=15.0,observability=None):
        self.llm_client=llm_client; self.dispatcher=dispatcher; self.observability=observability
        self.max_rounds=int(max_rounds); self.total_timeout_seconds=float(total_timeout_seconds)

    async def reason(self, *, request, context, pending_state, identity_user_id, conversation_history=None):
        async def run():
            reasoning_id=None; results=[]
            reasoning_context=build_reasoning_context(request,context,pending_state,conversation_history=conversation_history)
            for _ in range(self.max_rounds):
                if self.observability is not None:
                    self.observability.trace_event(
                        "LLM_PROVIDER_REQUEST",
                        request_id=request.request_id,
                        origin_request_id=request.origin_request_id or request.request_id,
                        trace_id=context.trace_id,
                        operation="llm.provider",
                        params={"purpose":"REASONING","round":len(results)+1},
                    )
                result=await self.llm_client.reason(LlmRequest(
                    purpose=LlmPurpose.REASONING,context=reasoning_context,
                    reasoning_id=reasoning_id,capability_results=results,
                ))
                if self.observability is not None:
                    self.observability.trace_event(
                        "LLM_PROVIDER_RESPONSE",
                        request_id=request.request_id,
                        origin_request_id=request.origin_request_id or request.request_id,
                        trace_id=context.trace_id,
                        operation="llm.provider",
                        result=result.outcome.value,
                        params={"purpose":"REASONING","reasoning_id":result.reasoning_id},
                    )
                if result.outcome is not ReasoningOutcome.NEEDS_CAPABILITY:
                    return result
                reasoning_id=result.reasoning_id
                capability=await self.dispatcher.execute(
                    result.capability_request,request=request,
                    identity_user_id=identity_user_id,context=context,trace_id=context.trace_id,
                )
                results=[capability]
            raise ReasoningBudgetExceeded("reasoning round budget exhausted")
        try:
            return await asyncio.wait_for(run(),timeout=self.total_timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise ReasoningBudgetExceeded("reasoning timeout") from exc
