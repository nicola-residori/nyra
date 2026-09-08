from datetime import datetime, timedelta, timezone

import pytest

from memory.embeddings import EmbeddingVector
from memory.semantic import SemanticMemoryService
from memory.storage import MemoryStore
from shared.protocol.memory import SemanticMemoryCreate


NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


class FakeEmbeddingProvider:
    provider_name = "fake"
    model_name = "fake-v1"

    def __init__(self):
        self.calls = []

    def embed(self, text):
        self.calls.append(text)
        return EmbeddingVector(
            values=(0.6, 0.8), provider=self.provider_name, model=self.model_name
        )


class FailingEmbeddingProvider(FakeEmbeddingProvider):
    def embed(self, text):
        raise RuntimeError("embedding failed")


def command(content, key, *, scope="USER", owner="user-nicola", memory_type="FACT"):
    return SemanticMemoryCreate(
        memory_type=memory_type,
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
    ticks = iter(NOW + timedelta(seconds=index) for index in range(30))
    provider = FakeEmbeddingProvider()
    service = SemanticMemoryService(store, provider, clock=lambda: next(ticks))
    return service, store, provider


def test_create_persists_content_vector_and_model_metadata(semantic):
    service, store, provider = semantic

    created = service.create(command("I prefer espresso", "write-1"))

    assert created.admission.value == "NEW"
    assert created.memory.memory_id.startswith("mem_")
    assert created.memory.content == "I prefer espresso"
    assert created.memory.embedding_provider == "fake"
    assert created.memory.embedding_model == "fake-v1"
    assert provider.calls == ["I prefer espresso"]
    with store.connect() as connection:
        row = connection.execute(
            "SELECT embedding, embedding_dimension FROM semantic_memories"
        ).fetchone()
    assert row["embedding"] is not None
    assert row["embedding_dimension"] == 2


def test_records_survive_store_reopen(tmp_path):
    path = tmp_path / "memory.sqlite3"
    first_store = MemoryStore(path)
    first_store.initialize()
    first = SemanticMemoryService(
        first_store, FakeEmbeddingProvider(), clock=lambda: NOW
    )
    created = first.create(command("I prefer espresso", "write-1"))

    second_store = MemoryStore(path)
    second_store.initialize()
    second = SemanticMemoryService(
        second_store, FakeEmbeddingProvider(), clock=lambda: NOW
    )

    assert second.get(created.memory.memory_id).content == "I prefer espresso"


def test_embedding_failure_leaves_no_partial_record(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    service = SemanticMemoryService(
        store, FailingEmbeddingProvider(), clock=lambda: NOW
    )

    with pytest.raises(RuntimeError, match="embedding failed"):
        service.create(command("I prefer espresso", "write-1"))

    assert service.list_memories().items == []
    with store.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM idempotency_results"
        ).fetchone()[0]
    assert count == 0


def test_same_content_in_different_scope_is_not_a_duplicate(semantic):
    service, _, _ = semantic
    user = service.create(command("Coffee at eight", "user-1"))
    family = service.create(
        command("Coffee at eight", "family-1", scope="FAMILY", owner=None)
    )

    assert user.memory.memory_id != family.memory.memory_id
    assert service.list_memories().total == 2


def test_list_filters_scope_owner_type_and_state(semantic):
    service, _, _ = semantic
    service.create(command("Coffee", "1", memory_type="PREFERENCE"))
    service.create(command("Office", "2", memory_type="NOTE"))
    service.create(command("Family", "3", scope="FAMILY", owner=None))

    page = service.list_memories(
        scope="USER", owner_user_id="user-nicola", memory_type="PREFERENCE"
    )

    assert page.total == 1
    assert page.items[0].content == "Coffee"

