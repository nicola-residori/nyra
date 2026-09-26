from __future__ import annotations
from router.lifecycle.service import LifecycleDecision
from router.llm_client import LlmUnavailable
from router.reasoning_orchestrator import ReasoningBudgetExceeded
from shared.protocol.llm import ReasoningOutcome
from shared.protocol.capabilities import CapabilityCorrelation
from shared.protocol.skills import SkillCorrelation
from shared.protocol.execution_common import ExecutionStatus

class RouterLlmPort:
    def __init__(self,orchestrator,action_gate=None,plan_executor=None):
        self.orchestrator=orchestrator; self.action_gate=action_gate; self.plan_executor=plan_executor

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
                if self.action_gate is None or self.plan_executor is None:
                    return LifecycleDecision.failed("LLM_ACTION_GATE_NOT_CONFIGURED")
                origin_request_id=request.origin_request_id or request.request_id
                skill_correlation=SkillCorrelation(request_id=request.request_id,origin_request_id=origin_request_id,trace_id=context.trace_id)
                capability_correlation=CapabilityCorrelation(request_id=request.request_id,origin_request_id=origin_request_id,trace_id=context.trace_id)
                trusted_context=context.data if isinstance(context.data,dict) else {}
                try:
                    validated=await self.action_gate.validate_proposal(result.proposed_execution_plan,correlation=skill_correlation,trusted_context=trusted_context)
                    executed=await self.plan_executor.execute(validated,correlation=capability_correlation,trusted_context=trusted_context)
                except ValueError as exc:
                    return LifecycleDecision.failed(str(exc))
                if executed.status is not ExecutionStatus.COMPLETED:
                    return LifecycleDecision.failed("LLM_ACTION_EXECUTION_FAILED")
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
