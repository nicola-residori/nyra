from datetime import datetime, timezone

import pytest

from memory.embeddings import EmbeddingModelMismatch, EmbeddingVector
from memory.semantic import SemanticMemoryService
from memory.storage import MemoryStore
from shared.protocol.memory import SemanticMemoryCreate, SemanticSearchRequest


NOW = datetime(2026, 9, 8, 14, 0, tzinfo=timezone.utc)


class VectorProvider:
    provider_name = "fake"
    model_name = "fake-v1"

    def __init__(self, vectors, *, model_name="fake-v1"):
        self.vectors = vectors
        self.model_name = model_name

    def embed(self, text):
        return EmbeddingVector(
            values=tuple(self.vectors[text]),
            provider=self.provider_name,
            model=self.model_name,
        )


def create(service, content, key, *, scope="FAMILY", owner=None, memory_type="FACT"):
    return service.create(
        SemanticMemoryCreate(
            memory_type=memory_type,
            scope=scope,
            owner_user_id=owner,
            content=content,
            source="USER_EXPLICIT",
            idempotency_key=key,
        )
    ).memory


def test_search_ranks_cosine_similarity_and_applies_threshold(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    provider = VectorProvider({
        "espresso": [1.0, 0.0],
        "coffee": [0.8, 0.6],
        "tea": [0.0, 1.0],
        "query": [1.0, 0.0],
    })
    service = SemanticMemoryService(store, provider, clock=lambda: NOW)
    espresso = create(service, "espresso", "1")
    coffee = create(service, "coffee", "2")
    create(service, "tea", "3")

    result = service.search(
        SemanticSearchRequest(
            query="query", scopes=["FAMILY"], minimum_similarity=0.7, limit=10
        )
    )

    assert [item.memory_id for item in result.items] == [
        espresso.memory_id, coffee.memory_id
    ]
    assert [item.score for item in result.items] == pytest.approx([1.0, 0.8])
    assert result.query_model == "fake-v1"


def test_scope_filter_excludes_other_users_before_ranking(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    provider = VectorProvider({
        "mine": [0.8, 0.6],
        "other": [1.0, 0.0],
        "family": [0.9, 0.43589],
        "query": [1.0, 0.0],
    })
    service = SemanticMemoryService(store, provider, clock=lambda: NOW)
    mine = create(service, "mine", "1", scope="USER", owner="user-a")
    create(service, "other", "2", scope="USER", owner="user-b")
    family = create(service, "family", "3")

    result = service.search(
        SemanticSearchRequest(
            query="query",
            scopes=["USER", "FAMILY"],
            owner_user_id="user-a",
            minimum_similarity=0,
        )
    )

    assert {item.memory_id for item in result.items} == {
        mine.memory_id, family.memory_id
    }
    assert all(item.owner_user_id in (None, "user-a") for item in result.items)


def test_search_filters_type_and_limits_results(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    provider = VectorProvider({
        "fact": [1.0, 0.0],
        "preference": [0.9, 0.43589],
        "query": [1.0, 0.0],
    })
    service = SemanticMemoryService(store, provider, clock=lambda: NOW)
    create(service, "fact", "1", memory_type="FACT")
    preference = create(service, "preference", "2", memory_type="PREFERENCE")

    result = service.search(
        SemanticSearchRequest(
            query="query",
            scopes=["FAMILY"],
            memory_types=["PREFERENCE"],
            minimum_similarity=0,
            limit=1,
        )
    )

    assert [item.memory_id for item in result.items] == [preference.memory_id]


def test_superseded_memories_are_excluded_from_search(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    provider = VectorProvider({
        "old": [1.0, 0.0],
        "new": [0.8, 0.6],
        "query": [1.0, 0.0],
    })
    service = SemanticMemoryService(store, provider, clock=lambda: NOW)
    old = create(service, "old", "1")
    replacement = SemanticMemoryCreate(
        memory_type="FACT",
        scope="FAMILY",
        content="new",
        source="USER_EXPLICIT",
        idempotency_key="inner",
    )
    new = service.supersede(old.memory_id, replacement, idempotency_key="2").memory

    result = service.search(
        SemanticSearchRequest(
            query="query", scopes=["FAMILY"], minimum_similarity=0
        )
    )

    assert [item.memory_id for item in result.items] == [new.memory_id]


def test_search_rejects_stored_vectors_from_another_model(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    writer = SemanticMemoryService(
        store, VectorProvider({"memory": [1.0, 0.0]}, model_name="old-v1"),
        clock=lambda: NOW,
    )
    create(writer, "memory", "1")
    reader = SemanticMemoryService(
        store, VectorProvider({"query": [1.0, 0.0]}, model_name="new-v2"),
        clock=lambda: NOW,
    )

    with pytest.raises(EmbeddingModelMismatch, match="old-v1"):
        reader.search(
            SemanticSearchRequest(
                query="query", scopes=["FAMILY"], minimum_similarity=0
            )
        )


def test_tied_scores_use_memory_id_for_stable_order(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    provider = VectorProvider({"one": [1, 0], "two": [1, 0], "query": [1, 0]})
    identifiers = iter((
        "mem_223e4567-e89b-42d3-a456-426614174000",
        "mem_123e4567-e89b-42d3-a456-426614174000",
    ))
    service = SemanticMemoryService(
        store, provider, clock=lambda: NOW, id_factory=lambda: next(identifiers)
    )
    create(service, "one", "1")
    create(service, "two", "2")

    result = service.search(
        SemanticSearchRequest(
            query="query", scopes=["FAMILY"], minimum_similarity=0
        )
    )

    assert [item.memory_id for item in result.items] == sorted(
        item.memory_id for item in result.items
    )

