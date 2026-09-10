import pytest

from router.lifecycle.service import ContextResult
from router.memory_client import MemoryUnavailable
from shared.protocol.ids import new_request_id, new_session_id
from shared.protocol.requests import (
    ExecutionType,
    NyraRequest,
    RequestInput,
    RequestStatus,
    TrustedIdentity,
)


def nyra_request(*, user_id="alice", language="en"):
    request_id = new_request_id()
    return NyraRequest(
        type=ExecutionType.HA_ASSIST,
        session_id=new_session_id(),
        request_id=request_id,
        origin_request_id=request_id,
        language=language,
        identity=TrustedIdentity(
            user_id=user_id,
            provider="home_assistant",
            confidence=1.0,
        ) if user_id else None,
        input=RequestInput(text="memory command"),
    )


def context(user_id="alice"):
    return ContextResult(
        data={
            "identity": {
                "user_id": user_id,
                "resolution_source": "TRUSTED_HA_IDENTITY",
            }
        }
    )


class FakeMemoryClient:
    def __init__(self, search_items=None, fail=False):
        self.search_items = search_items or []
        self.fail = fail
        self.calls = []

    async def json(self, method, path, *, params=None, payload=None):
        self.calls.append((method, path, payload))
        if self.fail:
            raise MemoryUnavailable("down")
        if path == "/v1/semantic/search":
            return {"items": self.search_items}
        if method == "POST" and path == "/v1/semantic/memories":
            return {"admission": "NEW", "memory": {"memory_id": "mem_created"}}
        if path.endswith("/supersede"):
            return {"admission": "SUPERSEDES", "memory": {"memory_id": "mem_new"}}
        if method == "DELETE":
            return {"memory_id": path.rsplit("/", 1)[-1], "state": "DELETED"}
        return {}


@pytest.mark.asyncio
async def test_remember_uses_router_canonical_user_scope_not_text_claim():
    from router.memory_skill_gateway import MemorySkillGateway
    memory = FakeMemoryClient()
    gateway = MemorySkillGateway(memory)

    result = await gateway.execute(
        request=nyra_request(user_id="alice"),
        context=context("alice"),
        operation={
            "kind": "MEMORY_MANAGEMENT",
            "operation": "REMEMBER",
            "content": "for user bob preferred temperature is 19 degrees",
            "memory_type": "PREFERENCE",
            "scope": "SYSTEM",
            "owner_user_id": "bob",
        },
    )

    assert result.status is RequestStatus.COMPLETED
    method, path, payload = memory.calls[-1]
    assert (method, path) == ("POST", "/v1/semantic/memories")
    assert payload["scope"] == "USER"
    assert payload["owner_user_id"] == "alice"
    assert payload["source"] == "USER_EXPLICIT"


@pytest.mark.asyncio
async def test_guest_cannot_claim_another_users_user_scope():
    from router.memory_skill_gateway import MemorySkillGateway
    memory = FakeMemoryClient()
    gateway = MemorySkillGateway(memory)

    result = await gateway.execute(
        request=nyra_request(user_id=None),
        context=context("guest"),
        operation={
            "kind": "MEMORY_MANAGEMENT",
            "operation": "REMEMBER",
            "content": "bob likes 19 degrees",
            "owner_user_id": "bob",
        },
    )

    assert result.status is RequestStatus.FAILED
    assert result.error["code"] == "MEMORY_USER_IDENTITY_REQUIRED"
    assert memory.calls == []


@pytest.mark.asyncio
async def test_one_unambiguous_destructive_candidate_can_delete():
    from router.memory_skill_gateway import MemorySkillGateway
    memory = FakeMemoryClient(search_items=[
        {
            "memory_id": "mem_target",
            "scope": "USER",
            "owner_user_id": "alice",
            "content": "my preferred temperature is 21 degrees",
            "score": 0.61,
        }
    ])
    gateway = MemorySkillGateway(memory)

    result = await gateway.execute(
        request=nyra_request(),
        context=context(),
        operation={
            "kind": "MEMORY_MANAGEMENT",
            "operation": "FORGET",
            "query": "my preferred temperature",
        },
    )

    assert result.status is RequestStatus.COMPLETED
    deletes = [call for call in memory.calls if call[0] == "DELETE"]
    assert len(deletes) == 1
    assert deletes[0][1] == "/v1/semantic/memories/mem_target"


@pytest.mark.asyncio
async def test_multiple_plausible_destructive_candidates_require_clarification():
    from router.memory_skill_gateway import MemorySkillGateway
    memory = FakeMemoryClient(search_items=[
        {
            "memory_id": "mem_one",
            "scope": "USER",
            "owner_user_id": "alice",
            "content": "my preferred temperature is 21 degrees",
            "score": 0.92,
        },
        {
            "memory_id": "mem_two",
            "scope": "USER",
            "owner_user_id": "alice",
            "content": "my preferred temperature upstairs is 19 degrees",
            "score": 0.87,
        },
    ])
    gateway = MemorySkillGateway(memory)

    result = await gateway.execute(
        request=nyra_request(),
        context=context(),
        operation={
            "kind": "MEMORY_MANAGEMENT",
            "operation": "FORGET",
            "query": "my preferred temperature",
        },
    )

    assert result.status is RequestStatus.NEEDS_CLARIFICATION
    assert result.pending_state["kind"] == "memory_management_clarification"
    assert len(result.pending_state["candidates"]) == 2
    assert not [call for call in memory.calls if call[0] == "DELETE"]


@pytest.mark.asyncio
async def test_similarity_score_alone_never_authorizes_delete():
    from router.memory_skill_gateway import MemorySkillGateway
    memory = FakeMemoryClient(search_items=[
        {
            "memory_id": "mem_wrong",
            "scope": "USER",
            "owner_user_id": "alice",
            "content": "my favorite coffee is espresso",
            "score": 0.999,
        }
    ])
    gateway = MemorySkillGateway(memory)

    result = await gateway.execute(
        request=nyra_request(),
        context=context(),
        operation={
            "kind": "MEMORY_MANAGEMENT",
            "operation": "FORGET",
            "query": "preferred temperature",
        },
    )

    assert result.status is RequestStatus.FAILED
    assert result.error["code"] == "MEMORY_NOT_FOUND"
    assert not [call for call in memory.calls if call[0] == "DELETE"]


@pytest.mark.asyncio
async def test_explicit_remember_memory_unavailable_never_false_confirms():
    from router.memory_skill_gateway import MemorySkillGateway
    memory = FakeMemoryClient(fail=True)
    gateway = MemorySkillGateway(memory)

    result = await gateway.execute(
        request=nyra_request(),
        context=context(),
        operation={
            "kind": "MEMORY_MANAGEMENT",
            "operation": "REMEMBER",
            "content": "my preferred temperature is 21 degrees",
            "memory_type": "PREFERENCE",
        },
    )

    assert result.status is RequestStatus.FAILED
    assert result.error["code"] == "MEMORY_UNAVAILABLE"
    assert result.text is None


@pytest.mark.asyncio
async def test_supersede_requires_unambiguous_existing_target():
    from router.memory_skill_gateway import MemorySkillGateway
    memory = FakeMemoryClient(search_items=[
        {
            "memory_id": "mem_old",
            "scope": "USER",
            "owner_user_id": "alice",
            "content": "my preferred temperature is 21 degrees",
            "score": 0.73,
        }
    ])
    gateway = MemorySkillGateway(memory)

    result = await gateway.execute(
        request=nyra_request(),
        context=context(),
        operation={
            "kind": "MEMORY_MANAGEMENT",
            "operation": "SUPERSEDE",
            "query": "my preferred temperature",
            "replacement": "my preferred temperature is 22 degrees",
            "memory_type": "PREFERENCE",
        },
    )

    assert result.status is RequestStatus.COMPLETED
    supersedes = [call for call in memory.calls if call[1].endswith("/supersede")]
    assert len(supersedes) == 1
    replacement = supersedes[0][2]["replacement"]
    assert replacement["scope"] == "USER"
    assert replacement["owner_user_id"] == "alice"
    assert replacement["content"] == "my preferred temperature is 22 degrees"


@pytest.mark.asyncio
async def test_clarification_selection_mutates_only_explicit_selected_candidate():
    from router.memory_skill_gateway import MemorySkillGateway
    memory = FakeMemoryClient()
    gateway = MemorySkillGateway(memory)
    pending = {
        "kind": "memory_management_clarification",
        "operation": "FORGET",
        "query": "preferred temperature",
        "replacement": None,
        "memory_type": "NOTE",
        "candidates": [
            {"memory_id": "mem_one", "content": "preferred temperature is 21"},
            {"memory_id": "mem_two", "content": "preferred temperature upstairs is 19"},
        ],
    }

    result = await gateway.execute(
        request=nyra_request(),
        context=context(),
        operation={
            "kind": "MEMORY_MANAGEMENT",
            "operation": "RESOLVE_CLARIFICATION",
            "selection": "the second",
        },
        pending_state=pending,
    )

    assert result.status is RequestStatus.COMPLETED
    deletes = [call for call in memory.calls if call[0] == "DELETE"]
    assert [call[1] for call in deletes] == ["/v1/semantic/memories/mem_two"]
