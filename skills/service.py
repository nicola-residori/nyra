from __future__ import annotations

import inspect
from typing import Any

from shared.protocol.common import ErrorDetail
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCheckResponse,
    SkillExecuteRequest,
    SkillExecuteResponse,
    SkillOutcome,
)


class SkillsService:
    """Local orchestration shell for Skills-owned dependencies."""

    def __init__(
        self,
        *,
        registry: Any = None,
        job_store: Any = None,
        scheduler: Any = None,
    ) -> None:
        self.registry = registry
        self.job_store = job_store
        self.scheduler = scheduler

    @staticmethod
    def _component_ready(component: Any) -> bool:
        if component is None:
            return True
        readiness = getattr(component, "is_ready", None)
        if readiness is None:
            return True
        return bool(readiness())

    def is_ready(self) -> bool:
        return all(
            self._component_ready(component)
            for component in (self.registry, self.job_store, self.scheduler)
        )

    async def check(self, request: SkillCheckRequest) -> SkillCheckResponse:
        if self.registry is None:
            return SkillCheckResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.MISS,
            )

        selected = self.registry.check(request)
        if selected is None:
            return SkillCheckResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.MISS,
            )

        definition = self.registry.get(selected.skill_name)
        if definition is None:
            return SkillCheckResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code="SKILL_NOT_FOUND"),
            )

        skill = getattr(definition.matcher, "__self__", None)
        if skill is None or not hasattr(skill, "match"):
            return SkillCheckResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code="SKILL_INVALID_DEFINITION"),
            )

        return SkillCheckResponse(
            correlation=request.correlation,
            outcome=SkillOutcome.HANDLED,
            match=skill.match(),
        )

    async def execute(
        self,
        request: SkillExecuteRequest,
    ) -> SkillExecuteResponse:
        if self.registry is None:
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code="SKILL_NOT_FOUND"),
            )

        skill_name = request.match.skill_name or request.match.token
        definition = (
            self.registry.get(skill_name)
            if isinstance(skill_name, str)
            else None
        )
        if definition is None:
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code="SKILL_NOT_FOUND"),
            )

        result = definition.executor(request)
        if inspect.isawaitable(result):
            result = await result

        return SkillExecuteResponse(
            correlation=request.correlation,
            outcome=SkillOutcome.HANDLED,
            text=result if isinstance(result, str) else None,
            result=result if isinstance(result, dict) else None,
        )
