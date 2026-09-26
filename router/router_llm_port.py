from __future__ import annotations
from router.lifecycle.service import LifecycleDecision
from router.llm_client import LlmUnavailable
from router.reasoning_orchestrator import ReasoningBudgetExceeded
from shared.protocol.llm import ReasoningOutcome

class RouterLlmPort:
    def __init__(self,orchestrator):
        self.orchestrator=orchestrator

    async def reason(self,request,context,memory,pending_state):
        del memory
        identity=(context.data.get("identity") or {}) if isinstance(context.data,dict) else {}
        user_id=identity.get("user_id")
        try:
            result=await self.orchestrator.reason(
                request=request,context=context,pending_state=pending_state,identity_user_id=user_id
            )
        except LlmUnavailable:
            return LifecycleDecision.failed("LLM_UNAVAILABLE")
        except ReasoningBudgetExceeded:
            return LifecycleDecision.failed("LLM_REASONING_BUDGET_EXCEEDED")
        if result.outcome is ReasoningOutcome.COMPLETED:
            if result.proposed_execution_plan is not None:
                return LifecycleDecision.failed("LLM_ACTION_REQUIRES_GATE")
            return LifecycleDecision.completed(result.response_text)
        if result.outcome is ReasoningOutcome.NEEDS_CLARIFICATION:
            return LifecycleDecision.needs_clarification(
                result.clarification.question,
                {"llm_clarification":{
                    "question":result.clarification.question,
                    "reason":result.clarification.reason,
                }},
            )
        if result.outcome is ReasoningOutcome.FAILED:
            return LifecycleDecision.failed(result.error.code)
        return LifecycleDecision.failed("LLM_INVALID_TERMINAL_OUTCOME")
