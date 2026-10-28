import httpx
import pytest
from fastapi import FastAPI
from shared.protocol.alerts import AlertRequest, AlertState
from router.alert_capability import AlertCapability
from router.api.alerts import router
from skills.alert_client import RouterAlertClient


@pytest.mark.asyncio
async def test_skills_router_ha_boundary_auth_and_payload():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.path == "/api/nyra/alerts"
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(200, json={"state": "ACCEPTED"})

    app = FastAPI()
    app.include_router(router)
    app.state.alert_capability = AlertCapability(
        "http://ha", "secret", transport=httpx.MockTransport(handler)
    )
    client = RouterAlertClient("http://router", transport=httpx.ASGITransport(app=app))
    response = await client.alert(
        AlertRequest(action="START", job_id="job_123", source_id="speaker-a")
    )
    assert response.state == AlertState.ACCEPTED
    assert b'"source_id":"speaker-a"' in seen[0].content


@pytest.mark.asyncio
async def test_missing_ha_is_explicit_offline_not_success():
    response = await AlertCapability(None, None).alert(
        AlertRequest(action="STATUS", job_id="job_123", source_id="a")
    )
    assert response.state == AlertState.OFFLINE


@pytest.mark.parametrize("value", [0, 61, -1])
def test_contract_rejects_audio_cap_outside_safe_range(value):
    with pytest.raises(ValueError):
        AlertRequest(action="START", job_id="job_123", source_id="a", max_seconds=value)
