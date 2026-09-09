from __future__ import annotations

import httpx
import pytest

from router.ha_capability import HomeAssistantApiClient, HomeAssistantCapabilityPort
from shared.protocol.capabilities import CapabilityCorrelation, ExecuteRequest
from shared.protocol.common import CommonOutcome
from shared.protocol.execution_common import NyraOperation, NyraResourceType
from shared.protocol.ids import new_request_id, new_trace_id


def correlation() -> CapabilityCorrelation:
    return CapabilityCorrelation(request_id=new_request_id(), trace_id=new_trace_id())


@pytest.mark.parametrize(
    ("resource_type", "operation", "entity_id", "service_path"),
    [
        (NyraResourceType.LIGHT, NyraOperation.TURN_ON, "light.target", "/api/services/light/turn_on"),
        (NyraResourceType.LIGHT, NyraOperation.TURN_OFF, "light.target", "/api/services/light/turn_off"),
        (NyraResourceType.SWITCH, NyraOperation.TURN_ON, "switch.target", "/api/services/switch/turn_on"),
        (NyraResourceType.SWITCH, NyraOperation.TURN_OFF, "switch.target", "/api/services/switch/turn_off"),
        (NyraResourceType.COVER, NyraOperation.OPEN, "cover.target", "/api/services/cover/open_cover"),
        (NyraResourceType.COVER, NyraOperation.CLOSE, "cover.target", "/api/services/cover/close_cover"),
        (NyraResourceType.SCRIPT, NyraOperation.TRIGGER, "script.target", "/api/services/script/turn_on"),
        (NyraResourceType.SCENE, NyraOperation.TRIGGER, "scene.target", "/api/services/scene/turn_on"),
    ],
)
@pytest.mark.asyncio
async def test_execute_revalidates_then_uses_internal_mapping(resource_type, operation, entity_id, service_path):
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET":
            return httpx.Response(200, json={"entity_id": entity_id, "state": "off", "attributes": {}})
        return httpx.Response(200, json=[])

    capability = HomeAssistantCapabilityPort(HomeAssistantApiClient("http://ha", "token", transport=httpx.MockTransport(handler)))
    result = await capability.execute(
        ExecuteRequest(correlation=correlation(), operation=operation, resource_id=entity_id, resource_type=resource_type),
        {},
    )
    assert result.outcome is CommonOutcome.SUCCESS
    assert calls == [("GET", f"/api/states/{entity_id}"), ("POST", service_path)]


@pytest.mark.asyncio
async def test_execute_denies_resource_outside_policy_before_side_effect():
    posts = []
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST": posts.append(request.url.path)
        return httpx.Response(200, json={"entity_id": "light.kitchen", "state": "off", "attributes": {}})
    capability = HomeAssistantCapabilityPort(HomeAssistantApiClient("http://ha", "token", transport=httpx.MockTransport(handler)))
    result = await capability.execute(
        ExecuteRequest(correlation=correlation(), operation=NyraOperation.TURN_ON, resource_id="light.kitchen", resource_type=NyraResourceType.LIGHT),
        {"allowed_resource_ids": ["light.office"]},
    )
    assert result.outcome is CommonOutcome.DENIED
    assert posts == []


@pytest.mark.asyncio
async def test_execute_unavailable_entity_has_no_side_effect():
    posts = []
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST": posts.append(request.url.path)
        return httpx.Response(200, json={"entity_id": "light.kitchen", "state": "unavailable", "attributes": {}})
    capability = HomeAssistantCapabilityPort(HomeAssistantApiClient("http://ha", "token", transport=httpx.MockTransport(handler)))
    result = await capability.execute(
        ExecuteRequest(correlation=correlation(), operation=NyraOperation.TURN_ON, resource_id="light.kitchen", resource_type=NyraResourceType.LIGHT),
        {},
    )
    assert result.outcome is CommonOutcome.UNAVAILABLE
    assert posts == []


@pytest.mark.asyncio
async def test_unsupported_operation_never_calls_native_service():
    posts = []
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST": posts.append(request.url.path)
        return httpx.Response(200, json={"entity_id": "light.kitchen", "state": "off", "attributes": {}})
    capability = HomeAssistantCapabilityPort(HomeAssistantApiClient("http://ha", "token", transport=httpx.MockTransport(handler)))
    result = await capability.execute(
        ExecuteRequest(correlation=correlation(), operation=NyraOperation.TOGGLE, resource_id="light.kitchen", resource_type=NyraResourceType.LIGHT),
        {},
    )
    assert result.outcome is CommonOutcome.UNSUPPORTED
    assert posts == []


@pytest.mark.asyncio
async def test_non_idempotent_timeout_is_unknown_outcome_and_not_retried():
    attempts = 0
    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.method == "GET":
            return httpx.Response(200, json={"entity_id": "script.party", "state": "off", "attributes": {}})
        attempts += 1
        raise httpx.ReadTimeout("uncertain", request=request)
    capability = HomeAssistantCapabilityPort(HomeAssistantApiClient("http://ha", "token", transport=httpx.MockTransport(handler)))
    result = await capability.execute(
        ExecuteRequest(correlation=correlation(), operation=NyraOperation.TRIGGER, resource_id="script.party", resource_type=NyraResourceType.SCRIPT),
        {},
    )
    assert result.outcome is CommonOutcome.UNKNOWN_OUTCOME
    assert attempts == 1
