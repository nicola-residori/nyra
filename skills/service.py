from __future__ import annotations

from typing import Any


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
