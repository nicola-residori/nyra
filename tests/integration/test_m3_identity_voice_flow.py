from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from router.lifecycle.events import InteractionEventBroker
from router.lifecycle.service import (
    ContextResult,
    LifecycleDecision,
    RequestLifecycleService,
    SkillMatch,
)
from router.lifecycle.store import RequestStateStore
from router.speaker_identity import SpeakerIdentityOutcome, SpeakerIdentityResult
from shared.protocol.ids import new_request_id, new_session_id
from shared.protocol.requests import NyraRequest, RequestStatus


class ContextPort:
    async def resolve(self, request, identity_user_id):
        return ContextResult(data={"resolved_user_id": identity_user_id})


class MemoryPort:
    async def search(self, request, identity_user_id, context):
        return {}


class SkillPort:
    def __init__(self):
        self.contexts = []

    async def check(self, request, context, memory, pending_state):
        self.contexts.append(context.data)
        return SkillMatch(matched=True, token="test")

    async def execute(self, match, request, context, memory, pending_state):
        return LifecycleDecision.completed("ok")


class LlmPort:
    async def reason(self, request, context, memory, pending_state):
        return LifecycleDecision.completed("ok")


class UnavailableIdentity:
    async def identify(self, request, trace_id):
        raise ConnectionError("speaker-id unavailable")


class SequenceIdentity:
    def __init__(self, *results):
        self.results = iter(results)

    async def identify(self, request, trace_id):
        return next(self.results)


def identified(user_id, score=0.9):
    return SpeakerIdentityResult(
        SpeakerIdentityOutcome.IDENTIFIED, user_id, score, "diag", None
    )


def not_recognized():
    return SpeakerIdentityResult(
        SpeakerIdentityOutcome.NOT_RECOGNIZED, None, 0.2, "diag", "BELOW_THRESHOLD"
    )


def make_request(*, session_id=None, text="che ore sono", language="it-IT"):
    return NyraRequest.model_validate({
        "type": "ha_speaker",
        "session_id": session_id or new_session_id(),
        "request_id": new_request_id(),
        "language": language,
        "source": {"id": "nyra-mansarda", "area": "mansarda"},
        "input": {"text": text},
    })


def make_service(tmp_path, identity_port, *, skill_port=None, identity_config=None):
    store = RequestStateStore(tmp_path / "router.db")
    store.initialize()
    skill = skill_port or SkillPort()
    return RequestLifecycleService(
        store=store,
        broker=InteractionEventBroker(),
        identity_port=identity_port,
        context_port=ContextPort(),
        memory_port=MemoryPort(),
        skill_port=skill,
        llm_port=LlmPort(),
        clock=lambda: datetime.now(timezone.utc),
        identity_config=identity_config,
    ), store, skill


@pytest.mark.asyncio
async def test_identity_service_unavailable_does_not_block_the_request(tmp_path):
    service, store, skill = make_service(tmp_path, UnavailableIdentity())
    request = make_request()

    response = await service.execute(request)

    assert response.status is RequestStatus.COMPLETED
    assert store.get(request.request_id).identity_user_id == "guest"
    assert skill.contexts[-1]["identity"] == {
        "user_id": "guest",
        "display_name": None,
        "resolution_source": "GUEST_FALLBACK",
    }


@pytest.mark.asyncio
async def test_simulated_speaker_requests_cover_identity_continuity_switch_and_guest(tmp_path):
    identity = SequenceIdentity(
        identified("user-a"),
        not_recognized(),
        identified("user-b"),
        not_recognized(),
    )
    service, store, skill = make_service(tmp_path, identity)
    session = new_session_id()

    first = make_request(session_id=session, text="che ore sono")
    continued = make_request(session_id=session, text="accendi la luce")
    switched = make_request(session_id=session, text="spegni la luce")
    fresh_guest = make_request(text="meteo")
    for item in (first, continued, switched, fresh_guest):
        assert (await service.execute(item)).status is RequestStatus.COMPLETED

    assert [store.get(item.request_id).identity_user_id for item in (
        first, continued, switched, fresh_guest
    )] == ["user-a", "user-a", "user-b", "guest"]
    assert [context["identity"]["resolution_source"] for context in skill.contexts] == [
        "SPEAKER_IDENTIFICATION",
        "SESSION_CONTINUITY",
        "SPEAKER_IDENTIFICATION",
        "GUEST_FALLBACK",
    ]


class ControlledIdentity:
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def identify(self, request, trace_id):
        self.started.set()
        await self.release.wait()
        return identified("user-a")


class SlowIdentity:
    async def identify(self, request, trace_id):
        await asyncio.sleep(0.03)
        return identified("late-user")


@pytest.mark.asyncio
async def test_runtime_timeout_is_snapshotted_and_late_identity_cannot_change_request(tmp_path):
    from router.identity_config import IdentityRuntimeConfigStore

    database = tmp_path / "router.db"
    runtime = IdentityRuntimeConfigStore(database, default_timeout_seconds=0.2)
    runtime.initialize()
    controlled = ControlledIdentity()
    service, store, _ = make_service(tmp_path, controlled, identity_config=runtime)
    first = make_request()

    in_flight = asyncio.create_task(service.execute(first))
    await controlled.started.wait()
    runtime.update_identification_timeout(0.005)
    await asyncio.sleep(0.01)
    controlled.release.set()
    await in_flight
    assert store.get(first.request_id).identity_user_id == "user-a"

    late_service, late_store, _ = make_service(
        tmp_path, SlowIdentity(), identity_config=runtime
    )
    late = make_request()
    await late_service.execute(late)
    assert late_store.get(late.request_id).identity_user_id == "guest"
    await asyncio.sleep(0.05)
    assert late_store.get(late.request_id).identity_user_id == "guest"
