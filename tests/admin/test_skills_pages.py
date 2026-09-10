from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from admin.app import create_app
from admin.client import RouterClient
from admin.config import AdminSettings


HA_SECRET = "RAW-HA-SECRET"


def app(*, seen=None, unavailable=False):
    async def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append((request.method, request.url.path))
        if unavailable:
            return httpx.Response(503, json={"detail": "Skills unavailable"})
        if request.url.path == "/v1/admin/skills":
            return httpx.Response(200, json={
                "service": {
                    "configured": True,
                    "ready": True,
                    "status": "ok",
                    "error": None,
                },
                "skills": [
                    {"name": "memory_management", "priority": 110, "enabled": True},
                    {"name": "home_assistant_action", "priority": 90, "enabled": True},
                ],
                "jobs": [{
                    "job_id": "job_demo",
                    "status": "FAILED",
                    "created_at": "2026-09-10T10:00:00Z",
                    "execute_at": "2026-09-10T10:01:00Z",
                    "started_at": "2026-09-10T10:01:01Z",
                    "finished_at": "2026-09-10T10:01:02Z",
                    "delay_seconds": 1.0,
                    "error": "TEST_FAILURE",
                    "request_id": None,
                    "origin_request_id": "req_123e4567-e89b-42d3-a456-426614174001",
                    "created_trace_id": "trc_123e4567-e89b-42d3-a456-426614174002",
                }],
                "capabilities": {
                    "home_assistant": {
                        "configured": True,
                        "operations": ["resolve", "execute"],
                    }
                },
            })
        return httpx.Response(404)

    return create_app(
        AdminSettings(),
        RouterClient("http://router", transport=httpx.MockTransport(handler)),
    )


def test_skills_page_exists_navigation_contains_skills_and_admin_uses_router_only():
    seen = []
    with TestClient(app(seen=seen)) as client:
        response = client.get("/skills")

    assert response.status_code == 200
    assert 'href="/skills"' in response.text
    assert ("GET", "/v1/admin/skills") in seen
    assert all("/v1/jobs" not in path for _, path in seen)
    assert all("skills.sqlite" not in path for _, path in seen)


def test_skills_page_renders_service_registered_skills_jobs_and_correlation():
    with TestClient(app()) as client:
        body = client.get("/skills").text

    assert "Skills" in body
    assert "READY" in body
    assert "memory_management" in body
    assert "home_assistant_action" in body
    assert "job_demo" in body
    assert "FAILED" in body
    assert "TEST_FAILURE" in body
    assert "2026-09-10T10:00:00Z" in body
    assert "2026-09-10T10:01:00Z" in body
    assert "req_123e4567-e89b-42d3-a456-426614174001" in body
    assert "trc_123e4567-e89b-42d3-a456-426614174002" in body
    assert "Home Assistant capability" in body


def test_raw_ha_token_is_never_rendered():
    with TestClient(app()) as client:
        body = client.get("/skills").text

    assert HA_SECRET not in body
    assert "Authorization" not in body
    assert "Bearer" not in body


def test_admin_code_has_no_direct_sqlite_or_skills_db_access():
    admin_root = Path("admin")
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in admin_root.rglob("*")
        if path.is_file() and path.suffix in {".py", ".html", ".js"}
    ).casefold()

    assert "sqlite3" not in source
    assert "skills_job_db" not in source
    assert "job_db_path" not in source
    assert "/v1/jobs" not in source


def test_skills_page_shows_router_dependency_error():
    with TestClient(app(unavailable=True)) as client:
        response = client.get("/skills")

    assert response.status_code == 200
    assert "Skills diagnostics unavailable" in response.text
