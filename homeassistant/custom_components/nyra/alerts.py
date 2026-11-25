"""Persistent deferred-audio ownership, independent of conversational sessions."""

import asyncio
from collections import defaultdict
from copy import deepcopy
import time
from shared.protocol.alerts import AlertRequest, AlertResponse, AlertState

_ACTIVE = {AlertState.ACCEPTED, AlertState.PLAYING}
_TERMINAL = {
    AlertState.COMPLETED,
    AlertState.STOPPED,
    AlertState.FAILED,
    AlertState.UNKNOWN_OUTCOME,
}


class AlertCoordinator:
    def __init__(self, backend, save, *, records=None):
        self.backend = backend
        self.save = save
        self.records = records or {}
        self._locks = defaultdict(asyncio.Lock)
        self._save_lock = asyncio.Lock()
        self._tasks = {}
        self._generations = {}

    def generation(self, source):
        return self._generations.get(source, 0)

    def active(self, source):
        return any(
            r["request"]["source_id"] == source and AlertState(r["state"]) in _ACTIVE
            for r in self.records.values()
        )

    async def _persist(self):
        async with self._save_lock:
            await self.save(deepcopy(self.records))

    async def restore(self):
        for job, record in self.records.items():
            if AlertState(record["state"]) not in _ACTIVE:
                continue
            request = AlertRequest.model_validate(record["request"])
            try:
                state = await self.backend.status(request)
            except Exception:
                state = None
            record["state"] = (
                state
                if state in {s.value for s in _ACTIVE | _TERMINAL}
                else AlertState.UNKNOWN_OUTCOME.value
            )
        await self._persist()

    async def _reconcile(self, record):
        if AlertState(record["state"]) not in _ACTIVE:
            return
        stored = AlertRequest.model_validate(record["request"])
        try:
            state = await self.backend.status(stored)
        except Exception:
            state = None
        if state in {s.value for s in _TERMINAL}:
            record["state"] = state
        elif time.time() > record["accepted_at"] + stored.max_seconds + 15:
            record["state"] = (
                AlertState.UNKNOWN_OUTCOME if record.get("sent") else AlertState.FAILED
            ).value
            record["error"] = "PLAYBACK_CONFIRMATION_EXPIRED"
            task = self._tasks.get(stored.job_id)
            if task:
                task.cancel()
        elif state in {s.value for s in _ACTIVE}:
            record["state"] = state
        await self._persist()

    async def handle(self, request):
        async with self._locks[request.source_id]:
            record = self.records.get(request.job_id)
            if record and record["request"]["source_id"] != request.source_id:
                return AlertResponse(state=AlertState.NOT_FOUND)
            if record:
                await self._reconcile(record)
            if request.action == "STATUS":
                return AlertResponse(
                    state=(
                        AlertState(record["state"]) if record else AlertState.NOT_FOUND
                    )
                )
            if request.action == "STOP":
                if not record:
                    return AlertResponse(state=AlertState.NOT_FOUND)
                if AlertState(record["state"]) in _ACTIVE:
                    record["stop_requested"] = True
                    await self._persist()
                    task = self._tasks.get(request.job_id)
                    if task:
                        task.cancel()
                    if not record.get("sent"):
                        record["state"] = AlertState.STOPPED.value
                        await self._persist()
                    else:
                        try:
                            await self.backend.stop(request)
                            state = await self.backend.status(request)
                            if state in {s.value for s in _TERMINAL}:
                                record["state"] = state
                                await self._persist()
                        except Exception:
                            pass  # Durable stop intent is retried by the scheduler.
                return AlertResponse(state=AlertState(record["state"]))
            if record:
                return AlertResponse(state=AlertState(record["state"]))
            # Notifications have no Skills poller: reconcile all source ownership
            # before BUSY so a lost terminal event can never block future jobs.
            for existing in self.records.values():
                if existing["request"]["source_id"] == request.source_id:
                    await self._reconcile(existing)
            if self.active(request.source_id):
                return AlertResponse(state=AlertState.BUSY)
            if not await self.backend.available(request.source_id):
                return AlertResponse(state=AlertState.OFFLINE)
            epoch = await self.backend.epoch(request.source_id)
            if not epoch:
                return AlertResponse(
                    state=AlertState.OFFLINE, error="AUDIO_EPOCH_UNAVAILABLE"
                )
            self._generations[request.source_id] = (
                self.generation(request.source_id) + 1
            )
            self.records[request.job_id] = {
                "state": AlertState.ACCEPTED.value,
                "request": request.model_dump(mode="json"),
                "accepted_at": time.time(),
                "epoch": epoch,
            }
            await self._persist()
            task = asyncio.create_task(self._deliver(request, epoch))
            self._tasks[request.job_id] = task
            task.add_done_callback(
                lambda done, job=request.job_id: self._tasks.pop(job, None)
            )
            return AlertResponse(state=AlertState.ACCEPTED)

    async def _deliver(self, request, epoch):
        try:
            url = await self.backend.prepare(request)
            async with self._locks[request.source_id]:
                if self.records[request.job_id][
                    "state"
                ] != AlertState.ACCEPTED.value or self.records[request.job_id].get(
                    "stop_requested"
                ):
                    return
                self.records[request.job_id]["sent"] = True
                await self._persist()
                await self.backend.play(request, url, epoch)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            async with self._locks[request.source_id]:
                record = self.records[request.job_id]
                if record["state"] in {s.value for s in _ACTIVE}:
                    record["error"] = type(exc).__name__
                    # A preparation error is known not to have reached the device.
                    # A send timeout keeps ownership until status/epoch/cutoff reconcile it.
                    if not record.get("sent"):
                        record["state"] = AlertState.FAILED.value
                    await self._persist()

    async def event(self, source, job, state):
        if state not in {s.value for s in _ACTIVE | _TERMINAL}:
            return
        async with self._locks[source]:
            record = self.records.get(job)
            if (
                not record
                or record["request"]["source_id"] != source
                or AlertState(record["state"]) in _TERMINAL
            ):
                return
            record["state"] = state
            await self._persist()

    async def wake(self, source, epoch=None):
        # Firmware emits this only after local audio ownership has been stopped.
        self._generations[source] = self.generation(source) + 1
        async with self._locks[source]:
            for job, record in self.records.items():
                if (
                    record["request"]["source_id"] == source
                    and AlertState(record["state"]) in _ACTIVE
                    and (epoch is None or record.get("epoch") != epoch)
                ):
                    record["state"] = AlertState.STOPPED.value
                    record["stop_requested"] = True
                    task = self._tasks.get(job)
                    if task:
                        task.cancel()
            await self._persist()

    async def shutdown(self):
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
