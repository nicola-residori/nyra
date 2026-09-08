from __future__ import annotations

import httpx
import pytest

from router.config import RouterSettings
from router.skills_client import SkillsClient, SkillsUnavailable
from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCorrelation,
    SkillExecuteRequest,
    SkillMatch,
    SkillOutcome,
)


def correlation() -> SkillCorrelation:
    return SkillCorrelation(
        request_id=new_request_id(),
        trace_id=new_trace_id(),
    )


@pytest.mark.asyncio
async def test_check_uses_typed_skills_path_and_sends_no_ha_credentials():
    request = SkillCheckRequest(
        correlation=correlation(),
        text="turn on the lamp",
        language="en",
    )

    async def handler(http_request: httpx.Request) -> httpx.Response:
        assert http_request.method == "POST"
        assert http_request.url.path == "/v1/skills/check"
        lowered = {key.lower() for key in http_request.headers.keys()}
        assert "authorization" not in lowered
        assert "x-ha-access" not in lowered
        assert "x-home-assistant-token" not in lowered
        return httpx.Response(
            200,
            json={
                "correlation": request.correlation.model_dump(mode="json"),
                "outcome": "MISS",
                "match": None,
                "error": None,
            },
        )

    client = SkillsClient(
        "http://skills.test",
        transport=httpx.MockTransport(handler),
    )

    response = await client.check(request)

    assert response.outcome is SkillOutcome.MISS
    assert response.match is None


@pytest.mark.asyncio
async def test_execute_uses_typed_skills_path():
    match = SkillMatch(
        matched=True,
        skill_name="light_control",
        token="tok_test",
    )
    request = SkillExecuteRequest(
        correlation=correlation(),
        match=match,
        text="turn on the lamp",
        language="en",
    )

    async def handler(http_request: httpx.Request) -> httpx.Response:
        assert http_request.method == "POST"
        assert http_request.url.path == "/v1/skills/execute"
        return httpx.Response(
            200,
            json={
                "correlation": request.correlation.model_dump(mode="json"),
                "outcome": "HANDLED",
                "text": "Done.",
                "result": {"ok": True},
                "pending_state": None,
                "error": None,
            },
        )

    client = SkillsClient(
        "http://skills.test",
        transport=httpx.MockTransport(handler),
    )

    response = await client.execute(request)

    assert response.outcome is SkillOutcome.HANDLED
    assert response.result == {"ok": True}


@pytest.mark.asyncio
async def test_transport_failure_is_unavailable_not_miss():
    request = SkillCheckRequest(
        correlation=correlation(),
        text="turn on the lamp",
        language="en",
    )

    async def handler(http_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("skills unavailable", request=http_request)

    client = SkillsClient(
        "http://skills.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(SkillsUnavailable):
        await client.check(request)


def test_router_settings_load_skills_url_and_timeout(monkeypatch):
    monkeypatch.setenv("NYRA_SKILLS_URL", "http://skills.internal:8090")
    monkeypatch.setenv("NYRA_SKILLS_TIMEOUT_SECONDS", "4.5")

    settings = RouterSettings.load()

    assert settings.skills_url == "http://skills.internal:8090"
    assert settings.skills_timeout_seconds == 4.5
