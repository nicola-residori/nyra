from __future__ import annotations

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
    def __init__(self): self.identities = []
    async def resolve(self, request, identity_user_id):
        self.identities.append(identity_user_id)
        return ContextResult(data={}, semantic_memory_required=False)


class MemoryPort:
    async def search(self, request, identity_user_id, context): return {}


class SkillPort:
    async def check(self, request, context, memory, pending_state):
        return SkillMatch(matched=True, token="local")
    async def execute(self, match, request, context, memory, pending_state):
        return LifecycleDecision.completed("ok")


class LlmPort:
    async def reason(self, request, context, memory, pending_state):
        return LifecycleDecision.completed("ok")


class SequenceIdentity:
    def __init__(self, results): self.results = list(results)
    async def identify(self, request, trace_id): return self.results.pop(0)


def identified(user):
    return SpeakerIdentityResult(SpeakerIdentityOutcome.IDENTIFIED, user, .90, "diag", None)


def uncertain(outcome=SpeakerIdentityOutcome.NOT_RECOGNIZED):
    return SpeakerIdentityResult(
        outcome, None,
        .30 if outcome is SpeakerIdentityOutcome.NOT_RECOGNIZED else None,
        "diag",
        "BELOW_THRESHOLD" if outcome is SpeakerIdentityOutcome.NOT_RECOGNIZED else "FAILED",
    )


def request(session_id, request_id):
    return NyraRequest.model_validate({
        "type": "ha_speaker",
        "session_id": session_id,
        "request_id": request_id,
        "language": "it",
        "source": {"id": "speaker-a", "area": "living-room"},
        "input": {"text": "ciao"},
    })


def service(tmp_path, identity):
    db = tmp_path / "router.db"
    store = RequestStateStore(db); store.initialize()
    IdentityRuntimeConfigStore = importlib.import_module("router.identity_config").IdentityRuntimeConfigStore
    runtime = IdentityRuntimeConfigStore(db, default_timeout_seconds=1.0); runtime.initialize()
    context = ContextPort()
    svc = RequestLifecycleService(
        store=store, broker=Broker(), identity_port=identity, context_port=context,
        memory_port=MemoryPort(), skill_port=SkillPort(), llm_port=LlmPort(),
        clock=lambda: datetime.now(timezone.utc), identity_config=runtime,
    )
    return svc, store, context


@pytest.mark.asyncio
async def test_same_session_uses_last_trusted_identity_but_new_session_does_not(tmp_path):
    identity = SequenceIdentity([
        identified("nicola"),
        uncertain(),
        identified("alice"),
        uncertain(SpeakerIdentityOutcome.FAILED),
        uncertain(),
    ])
    svc, store, context = service(tmp_path, identity)

    session = new_session_id()
    expected = [
        (new_request_id(), "nicola", "nicola"),
        (new_request_id(), "nicola", "nicola"),
        (new_request_id(), "alice", "alice"),
        (new_request_id(), "alice", "alice"),
    ]
    for request_id, user_id, trusted in expected:
        await svc.execute(request(session, request_id))
        state = store.get(request_id)
        assert state.identity_user_id == user_id
        assert state.last_trusted_user_id == trusted

    new_session = new_session_id()
    new_request = new_request_id()
    await svc.execute(request(new_session, new_request))
    new_state = store.get(new_request)
    assert new_state.identity_user_id == "guest"
    assert new_state.last_trusted_user_id is None
    assert context.identities == ["nicola", "nicola", "alice", "alice", "guest"]
