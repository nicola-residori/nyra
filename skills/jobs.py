from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from shared.protocol.capabilities import CapabilityCorrelation, ExecuteRequest
from shared.protocol.common import CommonOutcome
from shared.protocol.execution_common import NyraOperation, NyraResourceType
from shared.protocol.ids import new_trace_id
from types import SimpleNamespace
from shared.protocol.skills import JobStatus

from skills.job_store import JobRecord, JobStore


class UnsupportedJobStop(RuntimeError):
    pass


class JobScheduler:
    """Executes persisted ephemeral jobs only through the Router capability."""

    def __init__(
        self,
        store: JobStore,
        capability: Any = None,
        *,
        poll_interval_seconds: float = 0.25,
        observability: Any = None,
    ) -> None:
        self.store = store
        self.capability = capability
        self.poll_interval_seconds = poll_interval_seconds
        self.observability = observability
        self._worker: asyncio.Task | None = None

    def is_ready(self) -> bool:
        return self.store.is_ready()

    def _job_span(self, operation: str, job: JobRecord, trace_id: str, *, parent_span_id=None):
        if self.observability is None:
            return None
        correlation = SimpleNamespace(
            request_id=None,
            origin_request_id=job.origin_request_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
        )
        return self.observability.span(
            operation, correlation, params={"job_id": job.job_id}
        )

    def schedule_action(
        self,
        *,
        execute_at: datetime,
        origin_request_id: str,
        created_trace_id: str,
        operation: NyraOperation,
        resource_id: str,
        resource_type: NyraResourceType,
        trusted_context: dict[str, Any],
        parameters: dict[str, Any] | None = None,
    ) -> JobRecord:
        job = self.store.create_scheduled(
            execute_at=execute_at,
            origin_request_id=origin_request_id,
            request_id=None,
            created_trace_id=created_trace_id,
            payload={
                "kind": "ha_action",
                "operation": operation.value,
                "resource_id": resource_id,
                "resource_type": resource_type.value,
                "parameters": dict(parameters or {}),
                "trusted_context": dict(trusted_context),
            },
        )
        self._job_span("skills.job.schedule", job, created_trace_id)
        return job

    async def _execute_claimed(self, job: JobRecord) -> JobRecord:
        trace_id = new_trace_id()
        start_span_id = self._job_span("skills.job.start", job, trace_id)
        if self.capability is None:
            return self.store.set_terminal(
                job.job_id,
                JobStatus.FAILED,
                error="ROUTER_CAPABILITY_UNAVAILABLE",
            )

        payload = job.payload
        try:
            operation = NyraOperation(payload["operation"])
            resource_type = NyraResourceType(payload["resource_type"])
            resource_id = str(payload["resource_id"])
            parameters = dict(payload.get("parameters") or {})
            trusted_context = dict(payload.get("trusted_context") or {})
        except (KeyError, TypeError, ValueError):
            return self.store.set_terminal(
                job.job_id,
                JobStatus.FAILED,
                error="INVALID_JOB_PAYLOAD",
            )

        correlation = CapabilityCorrelation(
            request_id=None,
            origin_request_id=job.origin_request_id,
            trace_id=trace_id,
            parent_span_id=start_span_id,
        )
        try:
            response = await self.capability.execute(
                ExecuteRequest(
                    correlation=correlation,
                    operation=operation,
                    resource_id=resource_id,
                    resource_type=resource_type,
                    parameters=parameters,
                ),
                trusted_context,
            )
        except Exception as exc:
            return self.store.set_terminal(
                job.job_id,
                JobStatus.FAILED,
                error=f"CAPABILITY_EXCEPTION:{type(exc).__name__}",
            )

        if response.outcome is CommonOutcome.SUCCESS:
            self._job_span(
                "skills.job.complete", job, trace_id, parent_span_id=start_span_id
            )
            return self.store.set_terminal(job.job_id, JobStatus.COMPLETED)
        if response.outcome is CommonOutcome.UNKNOWN_OUTCOME:
            return self.store.set_terminal(
                job.job_id,
                JobStatus.UNKNOWN_OUTCOME,
                error=(
                    response.error.code
                    if response.error is not None
                    else "UNKNOWN_OUTCOME"
                ),
            )
        self._job_span(
            "skills.job.fail", job, trace_id, parent_span_id=start_span_id
        )
        return self.store.set_terminal(
            job.job_id,
            JobStatus.FAILED,
            error=(
                response.error.code
                if response.error is not None
                else response.outcome.value
            ),
        )

    async def run_due(
        self,
        *,
        now: datetime | None = None,
    ) -> list[JobRecord]:
        current = now or datetime.now(timezone.utc)
        results: list[JobRecord] = []
        for pending in self.store.list_due(current):
            claimed = self.store.claim_due(pending.job_id, now=current)
            if claimed is None:
                continue
            results.append(await self._execute_claimed(claimed))
        return results

    async def cancel_job(self, job_id: str) -> JobRecord | None:
        job = self.store.cancel(job_id)
        if job is not None:
            self._job_span("skills.job.cancel", job, new_trace_id())
        return job

    async def stop_job(self, job_id: str) -> JobRecord | None:
        job = self.store.get(job_id)
        if job is None:
            return None
        if job.status is not JobStatus.RUNNING:
            raise UnsupportedJobStop(
                "STOP is supported only for a RUNNING job with an explicit safe stop"
            )
        if not isinstance(job.payload.get("safe_stop"), dict):
            raise UnsupportedJobStop("job has no explicit safe stop operation")
        raise UnsupportedJobStop(
            "safe stop execution is not implemented for this job type"
        )

    async def start(self) -> None:
        self.store.recover_interrupted()
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run_loop())

    async def shutdown(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        try:
            await self._worker
        except asyncio.CancelledError:
            pass
        self._worker = None

    async def _run_loop(self) -> None:
        while True:
            await self.run_due()
            await asyncio.sleep(self.poll_interval_seconds)
