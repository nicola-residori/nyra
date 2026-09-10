from __future__ import annotations

from typing import Any, Protocol

from shared.protocol.execution import ExecutionPlan, ExecutionResult
from shared.protocol.execution_common import PlanOrigin


class SkillsPlanPort(Protocol):
    async def validate_and_execute(
        self,
        plan: ExecutionPlan,
        *,
        correlation,
        trusted_context: dict[str, Any],
    ) -> ExecutionResult: ...


class LlmActionGate:
    """Router-owned gate for future LLM-proposed side effects.

    The Router never executes an LLM plan directly. It delegates the proposal
    to the Skills validation/materialization boundary; only that boundary may
    reach Router-owned protected capabilities.
    """

    def __init__(self, skills_plan_port: SkillsPlanPort) -> None:
        self.skills_plan_port = skills_plan_port

    async def execute_proposal(
        self,
        plan: ExecutionPlan,
        *,
        correlation,
        trusted_context: dict[str, Any],
    ) -> ExecutionResult:
        if plan.origin is not PlanOrigin.REASONING_LLM:
            raise ValueError("LLM action gate accepts only LLM-origin plans")
        return await self.skills_plan_port.validate_and_execute(
            plan,
            correlation=correlation,
            trusted_context=trusted_context,
        )
