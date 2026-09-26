from __future__ import annotations
import asyncio
from shared.protocol.llm import LlmPurpose,LlmRequest,ReasoningOutcome
from router.reasoning_context import build_reasoning_context

class ReasoningBudgetExceeded(RuntimeError):
    pass

class ReasoningOrchestrator:
    def __init__(self,llm_client,dispatcher,max_rounds:int=3,total_timeout_seconds:float=15.0):
        self.llm_client=llm_client; self.dispatcher=dispatcher
        self.max_rounds=int(max_rounds); self.total_timeout_seconds=float(total_timeout_seconds)

    async def reason(self, *, request, context, pending_state, identity_user_id):
        async def run():
            reasoning_id=None; results=[]
            reasoning_context=build_reasoning_context(request,context,pending_state)
            for _ in range(self.max_rounds):
                result=await self.llm_client.reason(LlmRequest(
                    purpose=LlmPurpose.REASONING,context=reasoning_context,
                    reasoning_id=reasoning_id,capability_results=results,
                ))
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
