import json

import httpx
import pytest

from router.skills_client import SkillsClient


class FakeCapability:
    class Client:
        token = "RAW-HA-SECRET"
    client = Client()


@pytest.mark.asyncio
async def test_skills_client_diagnostics_reads_only_skills_service_endpoints():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/health":
            return httpx.Response(200, json={"service": "nyra-skills", "status": "ok"})
        if request.url.path == "/ready":
            return httpx.Response(200, json={"service": "nyra-skills", "status": "ready"})
        if request.url.path == "/v1/skills":
            return httpx.Response(200, json=[
                {"name": "identity_query", "priority": 50, "enabled": True},
                {"name": "memory_management", "priority": 110, "enabled": True},
            ])
        if request.url.path == "/v1/jobs":
            return httpx.Response(200, json=[{
                "job_id": "job_1",
                "status": "FAILED",
                "created_at": "2026-09-10T10:00:00Z",
                "execute_at": "2026-09-10T10:01:00Z",
                "started_at": "2026-09-10T10:01:01Z",
                "finished_at": "2026-09-10T10:01:02Z",
                "error": "TEST_FAILURE",
                "origin_request_id": "req_123e4567-e89b-42d3-a456-426614174001",
                "request_id": None,
                "created_trace_id": "trc_123e4567-e89b-42d3-a456-426614174002",
                "payload": {"secret": "must-not-be-exposed"},
            }])
        return httpx.Response(404)

    client = SkillsClient("http://skills", transport=httpx.MockTransport(handler))
    data = await client.diagnostics()

    assert seen == ["/health", "/ready", "/v1/skills", "/v1/jobs"]
    assert data["ready"] is True
    assert data["skills"][0]["name"] == "identity_query"
    assert data["jobs"][0]["status"] == "FAILED"


@pytest.mark.asyncio
async def test_router_facade_returns_status_skills_jobs_correlation_and_no_ha_secret():
    from router.skills_admin import SkillsAdminFacade

    class Client:
        async def diagnostics(self):
            return {
                "health": {"service": "nyra-skills", "status": "ok"},
                "ready": True,
                "skills": [
                    {"name": "home_assistant_action", "priority": 90, "enabled": True}
                ],
                "jobs": [{
                    "job_id": "job_1",
                    "status": "FAILED",
                    "created_at": "2026-09-10T10:00:00Z",
                    "execute_at": "2026-09-10T10:01:00Z",
                    "started_at": "2026-09-10T10:01:01Z",
                    "finished_at": "2026-09-10T10:01:02Z",
                    "error": "TEST_FAILURE",
                    "origin_request_id": "req_123e4567-e89b-42d3-a456-426614174001",
                    "request_id": None,
                    "created_trace_id": "trc_123e4567-e89b-42d3-a456-426614174002",
                    "payload": {"Authorization": "Bearer RAW-HA-SECRET"},
                }],
            }

    data = await SkillsAdminFacade(
        Client(),
        ha_capability=FakeCapability(),
    ).snapshot()

    assert data["service"]["ready"] is True
    assert data["skills"][0]["name"] == "home_assistant_action"
    assert data["jobs"][0]["status"] == "FAILED"
    assert data["jobs"][0]["error"] == "TEST_FAILURE"
    assert data["jobs"][0]["origin_request_id"].startswith("req_")
    assert data["jobs"][0]["created_trace_id"].startswith("trc_")
    assert data["capabilities"]["home_assistant"]["configured"] is True

    serialized = json.dumps(data)
    assert "RAW-HA-SECRET" not in serialized
    assert "Authorization" not in serialized
    assert "Bearer" not in serialized
    assert "payload" not in data["jobs"][0]


@pytest.mark.asyncio
async def test_router_facade_reports_unconfigured_skills_without_throwing():
    from router.skills_admin import SkillsAdminFacade

    data = await SkillsAdminFacade(None, ha_capability=None).snapshot()

    assert data["service"] == {
        "configured": False,
        "ready": False,
        "status": "unconfigured",
        "error": None,
    }
    assert data["skills"] == []
    assert data["jobs"] == []
    assert data["capabilities"]["home_assistant"]["configured"] is False
