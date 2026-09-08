import httpx
from fastapi.testclient import TestClient

from admin.app import create_app
from admin.client import RouterClient
from admin.config import AdminSettings


MEMORY_ID = "mem_123e4567-e89b-42d3-a456-426614174001"
ENTRY_ID = "memop_123e4567-e89b-42d3-a456-426614174002"


def app(*, unavailable=False, seen=None):
    async def handler(request):
        if seen is not None:
            seen.append((request.method, request.url.path, request.content))
        if unavailable:
            return httpx.Response(503, json={"detail": "Memory is unavailable"})
        if request.url.path.endswith("/memory/operational"):
            if request.method == "GET":
                return httpx.Response(200, json={
                    "items": [{
                        "entry_id": ENTRY_ID,
                        "entry_type": "ALIAS",
                        "scope": "USER",
                        "owner_user_id": "user-nicola",
                        "owner_display_name": "Nicola Residori",
                        "key": "scrivania",
                        "value": {"target": "light.office"},
                        "enabled": True,
                        "revision": 2,
                        "created_at": "2026-09-08T10:00:00Z",
                        "updated_at": "2026-09-08T11:00:00Z",
                    }],
                    "total": 1, "limit": 50, "offset": 0,
                })
            return httpx.Response(201, json={"entry_id": ENTRY_ID})
        if request.url.path.endswith("/memory/semantic/search"):
            return httpx.Response(200, json={
                "items": [{**semantic_item(), "score": 0.91}],
                "query_model": "test-v1", "minimum_similarity": 0.35,
            })
        if request.url.path.endswith("/memory/semantic"):
            if request.method == "GET":
                return httpx.Response(200, json={
                    "items": [semantic_item()],
                    "total": 1, "limit": 50, "offset": 0,
                })
            return httpx.Response(201, json={
                "admission": "NEW", "memory": semantic_item()
            })
        if "/memory/" in request.url.path:
            return httpx.Response(200, json={"outcome": "SUCCESS"})
        return httpx.Response(404)

    return create_app(
        AdminSettings(),
        RouterClient("http://router", transport=httpx.MockTransport(handler)),
    )


def semantic_item():
    return {
        "memory_id": MEMORY_ID,
        "memory_type": "PREFERENCE",
        "scope": "USER",
        "owner_user_id": "user-nicola",
        "owner_display_name": "Nicola Residori",
        "content": "Preferisco il caffè espresso.",
        "source": "USER_EXPLICIT",
        "state": "ACTIVE",
        "supersedes_memory_id": None,
        "superseded_by_memory_id": None,
        "created_at": "2026-09-08T10:00:00Z",
        "updated_at": "2026-09-08T11:00:00Z",
        "last_confirmed_at": "2026-09-08T11:00:00Z",
        "embedding_provider": "test",
        "embedding_model": "test-v1",
    }


def test_operational_page_shows_name_id_filters_form_and_revision():
    with TestClient(app()) as client:
        body = client.get("/memory/operational").text

    assert "Contesto operativo" in body
    assert "Nicola Residori" in body
    assert "user-nicola" in body
    assert "scrivania" in body
    assert "light.office" in body
    assert "Revisione 2" in body
    assert "Nuova regola" in body
    assert 'name="entry_type"' in body
    assert 'name="scope"' in body


def test_semantic_page_shows_name_id_history_search_score_and_exact_actions():
    with TestClient(app()) as client:
        body = client.get("/memory/semantic?q=caff%C3%A8").text
        script = client.get("/static/js/memory.js").text

    assert "Memoria semantica" in body
    assert "Nicola Residori" in body
    assert "user-nicola" in body
    assert "Preferisco il caffè espresso." in body
    assert "91%" in body
    assert "Conferma" in body
    assert "Sostituisci" in body
    assert "Elimina" in body
    assert MEMORY_ID in body
    assert "data-memory-id" in body
    assert "supersedes_memory_id" in script
    assert "similar_memory_id" not in script


def test_sidebar_contains_both_memory_pages():
    with TestClient(app()) as client:
        body = client.get("/memory/operational").text
    assert 'href="/memory/operational"' in body
    assert 'href="/memory/semantic"' in body


def test_memory_pages_show_router_dependency_error():
    with TestClient(app(unavailable=True)) as client:
        operational = client.get("/memory/operational")
        semantic = client.get("/memory/semantic")
    assert operational.status_code == 200
    assert "Memory" in operational.text
    assert "Memory" in semantic.text
    assert "fault" in operational.text


def test_admin_memory_proxy_uses_router_only_for_mutations():
    seen = []
    with TestClient(app(seen=seen)) as client:
        response = client.post(
            "/admin-api/memory/semantic",
            json={"content": "Preferisco il tè"},
        )
    assert response.status_code == 201
    assert any(path == "/v1/admin/memory/semantic" for _, path, _ in seen)
    assert all("memory.test" not in path for _, path, _ in seen)
