from datetime import datetime, timedelta, timezone

import pytest

from memory.embeddings import EmbeddingVector
from memory.operational import IdempotencyConflict
from memory.semantic import (
    SemanticMemoryNotFound,
    SemanticMemoryService,
    SemanticMemoryStateConflict,
)
from memory.storage import MemoryStore
from shared.protocol.memory import SemanticMemoryCreate, SemanticMemoryState


NOW = datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc)
TRACE_ID = "trc_123e4567-e89b-42d3-a456-426614174001"


class FakeEmbeddingProvider:
    provider_name = "fake"
    model_name = "fake-v1"

    def __init__(self):
        self.calls = []

    def embed(self, text):
        self.calls.append(text)
        return EmbeddingVector(values=(1.0, 0.0), provider="fake", model="fake-v1")


def command(content, key, *, scope="USER", owner="user-nicola"):
    return SemanticMemoryCreate(
        memory_type="FACT",
        scope=scope,
        owner_user_id=owner,
        content=content,
        source="USER_EXPLICIT",
        idempotency_key=key,
    )


@pytest.fixture
def semantic(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    ticks = iter(NOW + timedelta(seconds=index) for index in range(50))
    provider = FakeEmbeddingProvider()
    return (
        SemanticMemoryService(store, provider, clock=lambda: next(ticks)),
        store,
        provider,
    )


def test_exact_normalized_duplicate_confirms_without_new_record(semantic):
    service, _, provider = semantic
    first = service.create(command("I   prefer Espresso", "write-1"))
    duplicate = service.create(command("  i prefer espresso  ", "write-2"))

    assert duplicate.admission.value == "DUPLICATE"
    assert duplicate.memory.memory_id == first.memory.memory_id
    assert duplicate.memory.last_confirmed_at == NOW + timedelta(seconds=1)
    assert service.list_memories().total == 1
    assert provider.calls == ["I   prefer Espresso"]


def test_same_idempotency_key_replays_original_result(semantic):
    service, _, provider = semantic
    first = service.create_idempotent(command("I prefer espresso", "write-1"))
    replay = service.create_idempotent(command("I prefer espresso", "write-1"))

    assert replay.replayed is True
    assert replay.value == first.value
    assert provider.calls == ["I prefer espresso"]


def test_changed_content_with_same_idempotency_key_is_rejected(semantic):
    service, _, _ = semantic
    service.create(command("I prefer espresso", "write-1"))

    with pytest.raises(IdempotencyConflict):
        service.create(command("I prefer tea", "write-1"))


def test_supersession_is_atomic_and_preserves_history(semantic):
    service, _, _ = semantic
    old = service.create(command("I prefer espresso", "write-1")).memory

    result = service.supersede(
        old.memory_id,
        command("I prefer tea", "replacement-inner"),
        idempotency_key="supersede-1",
    )

    assert result.admission.value == "SUPERSEDES"
    current = result.memory
    previous = service.get(old.memory_id)
    assert current.state is SemanticMemoryState.ACTIVE
    assert current.supersedes_memory_id == old.memory_id
    assert previous.state is SemanticMemoryState.SUPERSEDED
    assert previous.superseded_by_memory_id == current.memory_id
    assert service.list_memories(state="ACTIVE").items == [current]
    assert service.list_memories(state="SUPERSEDED").items == [previous]


def test_supersession_requires_same_scope_and_owner(semantic):
    service, _, _ = semantic
    old = service.create(command("I prefer espresso", "write-1")).memory

    with pytest.raises(SemanticMemoryStateConflict):
        service.supersede(
            old.memory_id,
            command("Family prefers tea", "inner", scope="FAMILY", owner=None),
            idempotency_key="supersede-1",
        )

    assert service.get(old.memory_id).state is SemanticMemoryState.ACTIVE


def test_delete_physically_removes_sensitive_data_and_leaves_tombstone(semantic):
    service, store, _ = semantic
    created = service.create(command("Private note", "write-1")).memory

    result = service.delete(
        created.memory_id,
        idempotency_key="delete-1",
        trace_id=TRACE_ID,
    )

    assert result.state is SemanticMemoryState.DELETED
    assert result.memory_id == created.memory_id
    with store.connect() as connection:
        active = connection.execute(
            "SELECT * FROM semantic_memories WHERE memory_id = ?",
            (created.memory_id,),
        ).fetchone()
        tombstone = connection.execute(
            "SELECT * FROM semantic_tombstones WHERE memory_id = ?",
            (created.memory_id,),
        ).fetchone()
    assert active is None
    assert set(tombstone.keys()) == {
        "memory_id", "deleted_at", "deletion_trace_id"
    }
    assert service.get(created.memory_id) == result


def test_delete_replays_and_rejects_a_different_key_payload(semantic):
    service, _, _ = semantic
    created = service.create(command("Private note", "write-1")).memory
    first = service.delete_idempotent(
        created.memory_id, "delete-1", TRACE_ID
    )
    replay = service.delete_idempotent(
        created.memory_id, "delete-1", TRACE_ID
    )

    assert replay.replayed is True
    assert replay.value == first.value

    another_trace_replay = service.delete_idempotent(
        created.memory_id,
        "delete-1",
        "trc_123e4567-e89b-42d3-a456-426614174002",
    )
    assert another_trace_replay.replayed is True
    assert another_trace_replay.value == first.value


def test_confirm_updates_only_active_memory(semantic):
    service, _, _ = semantic
    old = service.create(command("Original", "write-1")).memory
    replacement = service.supersede(
        old.memory_id,
        command("Replacement", "inner"),
        idempotency_key="supersede-1",
    ).memory

    confirmed = service.confirm(replacement.memory_id, "confirm-1")
    assert confirmed.last_confirmed_at > replacement.last_confirmed_at

    with pytest.raises(SemanticMemoryStateConflict):
        service.confirm(old.memory_id, "confirm-old")


def test_missing_memory_is_distinct_from_invalid_state(semantic):
    service, _, _ = semantic
    with pytest.raises(SemanticMemoryNotFound):
        service.get("mem_123e4567-e89b-42d3-a456-426614174000")
