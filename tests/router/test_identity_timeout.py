from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import pytest

import importlib
from router.lifecycle.service import ContextResult, LifecycleDecision, RequestLifecycleService, SkillMatch
from router.lifecycle.store import RequestStateStore
from router.speaker_identity import SpeakerIdentityOutcome, SpeakerIdentityResult
from shared.protocol.requests import NyraRequest
from shared.protocol.ids import new_request_id, new_session_id


class Broker:
    async def publish_state(self, event): pass
    async def publish_identity_feedback(self, event): pass
    async def publish_session_closed(self, event): pass


class ContextPort:
    async def resolve(self, request, identity_user_id):
        return ContextResult(data={}, semantic_memory_required=False)


class MemoryPort:
    async def search(self, request, identity_user_id, context): return {}


class SkillPort:
    async def check(self, request, context, memory, pending_state):
        return SkillMatch(matched=True, token="x")
    async def execute(self, match, request, context, memory, pending_state):
        return LifecycleDecision.completed("ok")


class LlmPort:
    async def reason(self, request, context, memory, pending_state):
        return LifecycleDecision.completed("ok")


def identified(user):
    return SpeakerIdentityResult(SpeakerIdentityOutcome.IDENTIFIED, user, .9, "diag", None)


class ControlledIdentity:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
    async def identify(self, request, trace_id):
        self.started.set()
        await self.release.wait()
        return identified("nicola")


class SlowIdentity:
    def __init__(self, delay): self.delay = delay
    async def identify(self, request, trace_id):
        await asyncio.sleep(self.delay)
        return identified("alice")


def req(session, rid):
    return NyraRequest.model_validate({
        "type": "ha_speaker", "session_id": session, "request_id": rid,
        "language": "it", "source": {"id": "speaker-a", "area": "living-room"},
        "input": {"text": "ciao"},
    })


def make_service(db, identity, runtime):
    store = RequestStateStore(db); store.initialize()
    return RequestLifecycleService(
        store=store, broker=Broker(), identity_port=identity, context_port=ContextPort(),
        memory_port=MemoryPort(), skill_port=SkillPort(), llm_port=LlmPort(),
        clock=lambda: datetime.now(timezone.utc), identity_config=runtime,
    ), store


@pytest.mark.asyncio
async def test_timeout_snapshot_is_taken_when_identification_starts(tmp_path):
    db = tmp_path / "router.db"
    IdentityRuntimeConfigStore = importlib.import_module("router.identity_config").IdentityRuntimeConfigStore
    runtime = IdentityRuntimeConfigStore(db, default_timeout_seconds=.20); runtime.initialize()

    identity_a = ControlledIdentity()
    svc_a, store = make_service(db, identity_a, runtime)

    request_a = new_request_id()
    in_flight = asyncio.create_task(svc_a.execute(req(new_session_id(), request_a)))
    await identity_a.started.wait()
    updated = runtime.update_identification_timeout(.005)
    assert updated.revision == 2

    await asyncio.sleep(.02)
    identity_a.release.set()
    await in_flight
    assert store.get(request_a).identity_user_id == "nicola"

    svc_b, store_b = make_service(db, SlowIdentity(.05), runtime)
    request_b = new_request_id()
    await svc_b.execute(req(new_session_id(), request_b))
    assert store_b.get(request_b).identity_user_id == "guest"


@pytest.mark.asyncio
async def test_late_identity_result_cannot_mutate_resolved_request(tmp_path):
    db = tmp_path / "router.db"
    IdentityRuntimeConfigStore = importlib.import_module("router.identity_config").IdentityRuntimeConfigStore
    runtime = IdentityRuntimeConfigStore(db, default_timeout_seconds=.005); runtime.initialize()
    svc, store = make_service(db, SlowIdentity(.03), runtime)

    late_request = new_request_id()
    await svc.execute(req(new_session_id(), late_request))
    resolved = store.get(late_request)
    assert resolved.identity_user_id == "guest"
    assert resolved.last_trusted_user_id is None

    await asyncio.sleep(.05)
    still_resolved = store.get(late_request)
    assert still_resolved.identity_user_id == "guest"
    assert still_resolved.last_trusted_user_id is None
