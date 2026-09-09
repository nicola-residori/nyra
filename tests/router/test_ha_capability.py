from __future__ import annotations

import httpx
import pytest

from router.ha_capability import HomeAssistantApiClient, HomeAssistantCapabilityPort
from shared.protocol.capabilities import (
    CapabilityCorrelation,
    ResolveCardinality,
    ResolveStatus,
    ResourceReference,
)
from shared.protocol.execution_common import NyraResourceType
from shared.protocol.ids import new_request_id, new_trace_id
from skills.config import SkillsSettings


def correlation() -> CapabilityCorrelation:
    return CapabilityCorrelation(
        request_id=new_request_id(),
        trace_id=new_trace_id(),
    )


def test_skills_settings_have_no_home_assistant_credentials():
    fields = SkillsSettings.__dataclass_fields__

    assert "home_assistant_url" not in fields
    assert "home_assistant_token" not in fields
    assert "ha_url" not in fields
    assert "ha_token" not in fields


@pytest.mark.asyncio
async def test_resolve_one_returns_single_policy_allowed_match_and_keeps_ha_token_private():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json=[
                {
                    "entity_id": "light.kitchen",
                    "state": "off",
                    "attributes": {"friendly_name": "Kitchen Light"},
                },
                {
                    "entity_id": "light.kitchen_island",
                    "state": "off",
                    "attributes": {"friendly_name": "Kitchen Island Light"},
                },
                {
                    "entity_id": "switch.kitchen",
                    "state": "off",
                    "attributes": {"friendly_name": "Kitchen Switch"},
                },
            ],
        )

    client = HomeAssistantApiClient(
        "http://homeassistant.local:8123",
        "secret-token",
        transport=httpx.MockTransport(handler),
    )
    capability = HomeAssistantCapabilityPort(client)

    response = await capability.resolve(
        ResourceReference(
            reference="kitchen light",
            resource_type=NyraResourceType.LIGHT,
            cardinality=ResolveCardinality.ONE,
        ),
        trusted_context={
            "allowed_resource_ids": ["light.kitchen"],
        },
        correlation=correlation(),
    )

    assert seen["url"].endswith("/api/states")
    assert seen["authorization"] == "Bearer secret-token"
    assert response.status is ResolveStatus.RESOLVED
    assert [item.resource.resource_id for item in response.candidates] == [
        "light.kitchen"
    ]
    assert response.candidates[0].resource.name == "Kitchen Light"
    assert "secret-token" not in response.model_dump_json()


@pytest.mark.asyncio
async def test_resolve_one_returns_not_found_for_zero_matches():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "entity_id": "light.office",
                    "state": "off",
                    "attributes": {"friendly_name": "Office Light"},
                }
            ],
        )

    capability = HomeAssistantCapabilityPort(
        HomeAssistantApiClient(
            "http://ha",
            "token",
            transport=httpx.MockTransport(handler),
        )
    )

    response = await capability.resolve(
        ResourceReference(
            reference="kitchen light",
            resource_type=NyraResourceType.LIGHT,
        ),
        trusted_context={},
        correlation=correlation(),
    )

    assert response.status is ResolveStatus.NOT_FOUND
    assert response.candidates == []


@pytest.mark.asyncio
async def test_resolve_one_returns_ambiguous_for_multiple_matches():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "entity_id": "light.kitchen",
                    "state": "off",
                    "attributes": {"friendly_name": "Kitchen Light"},
                },
                {
                    "entity_id": "light.kitchen_island",
                    "state": "off",
                    "attributes": {"friendly_name": "Kitchen Island Light"},
                },
            ],
        )

    capability = HomeAssistantCapabilityPort(
        HomeAssistantApiClient(
            "http://ha",
            "token",
            transport=httpx.MockTransport(handler),
        )
    )

    response = await capability.resolve(
        ResourceReference(
            reference="kitchen light",
            resource_type=NyraResourceType.LIGHT,
            cardinality=ResolveCardinality.ONE,
        ),
        trusted_context={},
        correlation=correlation(),
    )

    assert response.status is ResolveStatus.AMBIGUOUS
    assert [item.resource.resource_id for item in response.candidates] == [
        "light.kitchen",
        "light.kitchen_island",
    ]


@pytest.mark.asyncio
async def test_resolve_many_must_be_explicit_and_returns_all_allowed_matches():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "entity_id": "switch.garden_a",
                    "state": "off",
                    "attributes": {"friendly_name": "Garden Pump A"},
                },
                {
                    "entity_id": "switch.garden_b",
                    "state": "off",
                    "attributes": {"friendly_name": "Garden Pump B"},
                },
            ],
        )

    capability = HomeAssistantCapabilityPort(
        HomeAssistantApiClient(
            "http://ha",
            "token",
            transport=httpx.MockTransport(handler),
        )
    )

    response = await capability.resolve(
        ResourceReference(
            reference="garden pump",
            resource_type=NyraResourceType.SWITCH,
            cardinality=ResolveCardinality.MANY,
        ),
        trusted_context={},
        correlation=correlation(),
    )

    assert response.status is ResolveStatus.RESOLVED
    assert [item.resource.resource_id for item in response.candidates] == [
        "switch.garden_a",
        "switch.garden_b",
    ]


@pytest.mark.asyncio
async def test_policy_filter_is_applied_before_cardinality_decision():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "entity_id": "light.kitchen",
                    "state": "off",
                    "attributes": {"friendly_name": "Kitchen Light"},
                },
                {
                    "entity_id": "light.kitchen_private",
                    "state": "off",
                    "attributes": {"friendly_name": "Kitchen Private Light"},
                },
            ],
        )

    capability = HomeAssistantCapabilityPort(
        HomeAssistantApiClient(
            "http://ha",
            "token",
            transport=httpx.MockTransport(handler),
        )
    )

    response = await capability.resolve(
        ResourceReference(
            reference="kitchen light",
            resource_type=NyraResourceType.LIGHT,
        ),
        trusted_context={"allowed_resource_ids": ["light.kitchen"]},
        correlation=correlation(),
    )

    assert response.status is ResolveStatus.RESOLVED
    assert response.candidates[0].resource.resource_id == "light.kitchen"


@pytest.mark.asyncio
async def test_resolved_resource_is_detached_from_native_ha_state_payload():
    native = {
        "entity_id": "light.kitchen",
        "state": "off",
        "attributes": {"friendly_name": "Kitchen Light"},
    }

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[native])

    capability = HomeAssistantCapabilityPort(
        HomeAssistantApiClient(
            "http://ha",
            "token",
            transport=httpx.MockTransport(handler),
        )
    )

    response = await capability.resolve(
        ResourceReference(
            reference="kitchen light",
            resource_type=NyraResourceType.LIGHT,
        ),
        trusted_context={},
        correlation=correlation(),
    )

    native["entity_id"] = "light.changed"
    native["attributes"]["friendly_name"] = "Changed"

    assert response.candidates[0].resource.resource_id == "light.kitchen"
    assert response.candidates[0].resource.name == "Kitchen Light"
