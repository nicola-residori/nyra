from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from router.api.memory_admin import router
from router.memory_client import MemoryUnavailable


MEMORY_ID = "mem_123e4567-e89b-42d3-a456-426614174001"
ENTRY_ID = "memop_123e4567-e89b-42d3-a456-426614174002"


class Directory:
    def get(self, provider, user_id):
        if provider == "home_assistant" and user_id == "user-nicola":
            return SimpleNamespace(display_name="Nicola Residori")
        return None


class Memory:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    async def json(self, method, path, *, params=None, payload=None):
        self.calls.append((method, path, params, payload))
        if self.error:
            raise self.error
        return self.responses.pop(0)


def app(memory, token=None):
    result = FastAPI()
    result.state.settings = SimpleNamespace(ingress_token=token)
    result.state.memory_client = memory
    result.state.user_directory = Directory()
    result.include_router(router)
    return result


def semantic_payload(**extra):
    return {
        "memory_type": "PREFERENCE",
        "scope": "USER",
        "owner_user_id": "user-nicola",
        "content": "Preferisco il caffè espresso.",
        "source": "USER_EXPLICIT",
        "idempotency_key": "semantic-1",
        **extra,
    }


def semantic_memory():
    return {
        "memory_id": MEMORY_ID,
        "memory_type": "PREFERENCE",
        "scope": "USER",
        "owner_user_id": "user-nicola",
        "content": "Preferisco il caffè espresso.",
        "source": "USER_EXPLICIT",
        "state": "ACTIVE",
        "supersedes_memory_id": None,
        "superseded_by_memory_id": None,
        "created_at": "2026-09-08T10:00:00Z",
        "updated_at": "2026-09-08T10:00:00Z",
        "last_confirmed_at": "2026-09-08T10:00:00Z",
        "deleted_at": None,
        "embedding_provider": "test",
        "embedding_model": "test-v1",
    }


def test_create_semantic_memory_enriches_owner_name():
    memory = Memory([{"admission": "NEW", "memory": semantic_memory()}])
    response = TestClient(app(memory)).post(
        "/v1/admin/memory/semantic", json=semantic_payload()
    )

    assert response.status_code == 201
    assert response.json()["memory"]["owner_display_name"] == "Nicola Residori"
    assert response.json()["memory"]["owner_user_id"] == "user-nicola"
    assert memory.calls[0][1] == "/v1/semantic/memories"


def test_exact_duplicate_result_is_preserved():
    memory = Memory([{"admission": "DUPLICATE", "memory": semantic_memory()}])
    response = TestClient(app(memory)).post(
        "/v1/admin/memory/semantic", json=semantic_payload()
    )
    assert response.status_code == 200
    assert response.json()["admission"] == "DUPLICATE"
    assert response.json()["memory"]["memory_id"] == MEMORY_ID


def test_supersession_requires_and_uses_explicit_exact_memory_id():
    replacement = semantic_memory() | {"supersedes_memory_id": MEMORY_ID}
    memory = Memory([{"admission": "SUPERSEDES", "memory": replacement}])
    response = TestClient(app(memory)).post(
        "/v1/admin/memory/semantic",
        json=semantic_payload(
            supersedes_memory_id=MEMORY_ID,
            idempotency_key="supersede-1",
        ),
    )

    assert response.status_code == 201
    method, path, _, payload = memory.calls[0]
    assert (method, path) == (
        "POST", f"/v1/semantic/memories/{MEMORY_ID}/supersede"
    )
    assert payload["idempotency_key"] == "supersede-1"
    assert "supersedes_memory_id" not in payload["replacement"]


def test_similarity_hint_cannot_select_destructive_target():
    response = TestClient(app(Memory())).post(
        "/v1/admin/memory/semantic",
        json=semantic_payload(similar_memory_id=MEMORY_ID),
    )
    assert response.status_code == 422


def test_semantic_listing_enriches_names_and_forwards_filters():
    memory = Memory([{
        "items": [semantic_memory()], "total": 1, "limit": 20, "offset": 0
    }])
    response = TestClient(app(memory)).get(
        "/v1/admin/memory/semantic?scope=USER&owner_user_id=user-nicola&limit=20"
    )
    assert response.json()["items"][0]["owner_display_name"] == "Nicola Residori"
    assert memory.calls[0][2]["scope"] == "USER"
    assert memory.calls[0][2]["limit"] == 20


def test_operational_crud_is_proxied_with_owner_name():
    item = {
        "entry_id": ENTRY_ID,
        "entry_type": "ALIAS",
        "scope": "USER",
        "owner_user_id": "user-nicola",
        "key": "scrivania",
        "value": {"target": "light.office"},
        "enabled": True,
        "revision": 1,
        "created_at": "2026-09-08T10:00:00Z",
        "updated_at": "2026-09-08T10:00:00Z",
    }
    memory = Memory([item])
    response = TestClient(app(memory)).post(
        "/v1/admin/memory/operational",
        json={
            "entry_type": "ALIAS", "scope": "USER",
            "owner_user_id": "user-nicola", "key": "scrivania",
            "value": {"target": "light.office"}, "enabled": True,
            "idempotency_key": "alias-1",
        },
    )
    assert response.status_code == 201
    assert response.json()["owner_display_name"] == "Nicola Residori"


def test_semantic_search_is_validated_proxied_and_enriched():
    item = semantic_memory() | {"score": 0.91}
    memory = Memory([{
        "items": [item], "query_model": "test-v1", "minimum_similarity": 0.35
    }])
    response = TestClient(app(memory)).post(
        "/v1/admin/memory/semantic/search",
        json={
            "query": "caffè",
            "scopes": ["USER", "FAMILY"],
            "owner_user_id": "user-nicola",
        },
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["owner_display_name"] == "Nicola Residori"
    assert memory.calls[0][1] == "/v1/semantic/search"


def test_memory_dependency_failure_is_explicit_and_admin_auth_is_preserved():
    unavailable = TestClient(app(Memory(error=MemoryUnavailable("offline")))).get(
        "/v1/admin/memory/semantic"
    )
    assert unavailable.status_code == 503
    assert unavailable.json()["detail"] == "Memory is unavailable"

    unauthorized = TestClient(app(Memory(), token="secret")).get(
        "/v1/admin/memory/semantic"
    )
    assert unauthorized.status_code == 401
