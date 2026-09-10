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

from shared.protocol.common import CommonOutcome

@pytest.mark.asyncio
async def test_automation_transport_uses_nyra_adapter_endpoint():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path == "/api/nyra/automations":
            return httpx.Response(200, json=[])
        if request.method == "POST":
            return httpx.Response(200, json=request.json() if hasattr(request, "json") else {})
        return httpx.Response(200, json={"result": "ok"})

    client = HomeAssistantApiClient(
        "http://homeassistant.local:8123",
        "secret-token",
        transport=httpx.MockTransport(handler),
    )

    assert await client.automation_list() == []
    assert seen == [("GET", "/api/nyra/automations")]


@pytest.mark.asyncio
async def test_create_automation_marks_nyra_ownership_and_one_shot_cleanup():
    from shared.protocol.behavior import (
        Behavior,
        BehaviorAction,
        BehaviorActionType,
        BehaviorLifecycle,
        BehaviorTrigger,
    )
    from shared.protocol.capabilities import AutomationCreateRequest
    from shared.protocol.execution_common import ExecutionStep, NyraOperation

    class FakeClient:
        def __init__(self):
            self.writes = []

        async def automation_list(self):
            return []

        async def automation_write(self, automation_id, config):
            self.writes.append((automation_id, config))
            return config

    fake = FakeClient()
    capability = HomeAssistantCapabilityPort(fake)
    behavior = Behavior(
        behavior_id="morning",
        lifecycle=BehaviorLifecycle.ONE_SHOT,
        triggers=[BehaviorTrigger(kind="time", expression="2026-09-11T07:30:00+02:00")],
        actions=[
            BehaviorAction(
                type=BehaviorActionType.ACTION,
                action=ExecutionStep(
                    step_id="a",
                    operation=NyraOperation.TURN_ON,
                    target={
                        "reference": "desk light",
                        "resource_type": NyraResourceType.LIGHT,
                        "resolved": {
                            "resource_id": "light.desk",
                            "resource_type": NyraResourceType.LIGHT,
                            "semantic_reference": "desk light",
                        },
                    },
                ),
            )
        ],
    )

    response = await capability.create_automation(
        AutomationCreateRequest(correlation=correlation(), behavior=behavior),
        {},
    )

    assert response.outcome is CommonOutcome.SUCCESS
    automation_id, native = fake.writes[0]
    assert automation_id.startswith("nyra_")
    assert native["description"].startswith("[NYRA managed_by=NYRA ")
    assert native["actions"][-1] == {
        "action": "nyra.complete_one_shot",
        "data": {"automation_id": automation_id},
    }


@pytest.mark.asyncio
async def test_probable_equivalent_manual_automation_requires_clarification():
    from shared.protocol.behavior import (
        Behavior,
        BehaviorAction,
        BehaviorActionType,
        BehaviorLifecycle,
        BehaviorTrigger,
    )
    from shared.protocol.capabilities import AutomationCreateRequest
    from shared.protocol.execution_common import ExecutionStep, NyraOperation

    class FakeClient:
        async def automation_list(self):
            return [{
                "id": "manual",
                "alias": "Manual",
                "triggers": [{"trigger": "time", "at": "07:30:00"}],
                "conditions": [],
                "actions": [{"action": "light.turn_on", "target": {"entity_id": "light.desk"}}],
            }]
        async def automation_write(self, automation_id, config):
            raise AssertionError("must not duplicate probable manual equivalent")

    behavior = Behavior(
        behavior_id="daily",
        lifecycle=BehaviorLifecycle.PERSISTENT,
        triggers=[BehaviorTrigger(kind="time", expression="07:30:00")],
        actions=[
            BehaviorAction(
                type=BehaviorActionType.ACTION,
                action=ExecutionStep(
                    step_id="a",
                    operation=NyraOperation.TURN_ON,
                    target={
                        "reference": "desk light",
                        "resource_type": NyraResourceType.LIGHT,
                        "resolved": {
                            "resource_id": "light.desk",
                            "resource_type": NyraResourceType.LIGHT,
                            "semantic_reference": "desk light",
                        },
                    },
                ),
            )
        ],
    )
    response = await HomeAssistantCapabilityPort(FakeClient()).create_automation(
        AutomationCreateRequest(correlation=correlation(), behavior=behavior),
        {},
    )
    assert response.outcome is CommonOutcome.AMBIGUOUS
    assert response.error.code == "PROBABLE_EQUIVALENT_AUTOMATION"


@pytest.mark.asyncio
async def test_manual_automation_cannot_be_updated_or_deleted():
    from shared.protocol.behavior import Behavior, BehaviorLifecycle
    from shared.protocol.capabilities import AutomationDeleteRequest, AutomationUpdateRequest

    class FakeClient:
        async def automation_read(self, automation_id):
            return {"id": automation_id, "alias": "Manual automation"}

        async def automation_write(self, automation_id, config):
            raise AssertionError("manual automation must not be updated")

        async def automation_delete(self, automation_id):
            raise AssertionError("manual automation must not be deleted")

    capability = HomeAssistantCapabilityPort(FakeClient())
    behavior = Behavior(
        behavior_id="x",
        lifecycle=BehaviorLifecycle.PERSISTENT,
        triggers=[],
        actions=[],
    )
    update = await capability.update_automation(
        AutomationUpdateRequest(
            correlation=correlation(),
            automation_id="manual",
            behavior=behavior,
        ),
        {},
    )
    delete = await capability.delete_automation(
        AutomationDeleteRequest(
            correlation=correlation(),
            automation_id="manual",
        ),
        {},
    )
    assert update.outcome is CommonOutcome.DENIED
    assert delete.outcome is CommonOutcome.DENIED
