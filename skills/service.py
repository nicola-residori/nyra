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
        observability: Any = None,
    ) -> None:
        self.registry = registry
        self.job_store = job_store
        self.scheduler = scheduler
        self.observability = observability

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

    async def start(self) -> None:
        if self.scheduler is None:
            return
        start = getattr(self.scheduler, "start", None)
        if start is None:
            return
        result = start()
        if inspect.isawaitable(result):
            await result

    async def shutdown(self) -> None:
        if self.scheduler is None:
            return
        shutdown = getattr(self.scheduler, "shutdown", None)
        if shutdown is None:
            return
        result = shutdown()
        if inspect.isawaitable(result):
            await result

    def list_jobs(self):
        return self.job_store.list() if self.job_store is not None else []

    def get_job(self, job_id: str):
        return self.job_store.get(job_id) if self.job_store is not None else None

    async def cancel_job(self, job_id: str):
        if self.scheduler is None:
            return None
        return await self.scheduler.cancel_job(job_id)

    async def stop_job(self, job_id: str):
        if self.scheduler is None:
            return None
        return await self.scheduler.stop_job(job_id)

    async def check(self, request: SkillCheckRequest) -> SkillCheckResponse:
        if self.observability is not None:
            self.observability.span("skills.check", request.correlation)
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

        match = skill.match(request)
        return SkillCheckResponse(
            correlation=request.correlation,
            outcome=SkillOutcome.HANDLED,
            match=match,
        )

    async def execute(
        self,
        request: SkillExecuteRequest,
    ) -> SkillExecuteResponse:
        if self.observability is not None:
            execute_span_id = self.observability.span(
                "skills.execute", request.correlation
            )
            request = request.model_copy(
                update={
                    "correlation": request.correlation.model_copy(
                        update={"parent_span_id": execute_span_id}
                    )
                }
            )
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

        if isinstance(result, SkillExecuteResponse):
            return result

        return SkillExecuteResponse(
            correlation=request.correlation,
            outcome=SkillOutcome.HANDLED,
            text=result if isinstance(result, str) else None,
            result=result if isinstance(result, dict) else None,
        )
