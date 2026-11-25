"""Restart-aware alert job driver. No Home Assistant credentials live here."""

from datetime import datetime, timezone
from shared.protocol.alerts import AlertRequest, AlertState
from shared.protocol.capabilities import CapabilityCorrelation
from shared.protocol.ids import new_trace_id
from shared.protocol.skills import JobStatus

_TERMINAL = {
    AlertState.COMPLETED: JobStatus.COMPLETED,
    AlertState.STOPPED: JobStatus.STOPPED,
    AlertState.FAILED: JobStatus.FAILED,
    AlertState.UNKNOWN_OUTCOME: JobStatus.UNKNOWN_OUTCOME,
}


class AlertJobs:
    def __init__(self, store, capability, *, offline_grace_seconds=60):
        self.store = store
        self.capability = capability
        self.offline_grace_seconds = offline_grace_seconds

    async def _call(self, job, action):
        payload = job.payload
        return await self.capability.alert(
            AlertRequest(
                action=action,
                job_id=job.job_id,
                source_id=payload["source_id"],
                alert_kind=payload["alert_kind"],
                language=payload["language"],
                message=payload.get("message"),
                max_seconds=payload["max_seconds"],
                correlation=CapabilityCorrelation(
                    origin_request_id=job.origin_request_id, trace_id=new_trace_id()
                ),
            )
        )

    async def tick(self, job, now, *, fresh=False):
        try:
            response = await self._call(
                job, "STOP" if job.payload.get("stop_requested") else "STATUS"
            )
            if response.state == AlertState.NOT_FOUND:
                if not fresh:
                    return self.store.set_terminal(
                        job.job_id,
                        JobStatus.UNKNOWN_OUTCOME,
                        error="PLAYBACK_STATE_LOST",
                    )
                # Mark delivery intent durably before sending. A timeout is ambiguous.
                response = await self._call(job, "START")
            if response.state in _TERMINAL:
                return self.store.set_terminal(
                    job.job_id, _TERMINAL[response.state], error=response.error
                )
            if response.state in (AlertState.OFFLINE, AlertState.BUSY):
                if (now - job.execute_at).total_seconds() > self.offline_grace_seconds:
                    return self.store.set_terminal(
                        job.job_id,
                        JobStatus.FAILED,
                        error=(
                            "SPEAKER_OFFLINE_EXPIRED"
                            if response.state == AlertState.OFFLINE
                            else "SPEAKER_BUSY_EXPIRED"
                        ),
                    )
                # OFFLINE/BUSY explicitly guarantee no delivery accepted. Only these may retry.
                if fresh:
                    self.store.reschedule_alert(job.job_id)
            return self.store.get(job.job_id)
        except Exception as exc:
            # Remain RUNNING so next tick asks status, never blindly resends START.
            if (now - job.execute_at).total_seconds() > self.offline_grace_seconds + 60:
                return self.store.set_terminal(
                    job.job_id,
                    JobStatus.UNKNOWN_OUTCOME,
                    error=f"AUDIO_UNREACHABLE:{type(exc).__name__}",
                )
            return self.store.get(job.job_id)

    async def stop(self, job):
        self.store.update_alert_payload(job.job_id, {"stop_requested": True})
        return await self.tick(self.store.get(job.job_id), datetime.now(timezone.utc))
