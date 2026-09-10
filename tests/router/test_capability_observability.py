import json

import pytest

from shared.protocol.capabilities import (
    CapabilityCorrelation,
    ExecuteRequest,
    ResourceReference,
)
from shared.protocol.execution_common import NyraOperation, NyraResourceType
from shared.protocol.ids import new_request_id, new_span_id, new_trace_id


class RecordingObservability:
    def __init__(self):
        self.records = []

    def ingest(self, records):
        self.records.extend(records)
        return len(records)


class Client:
    token = "SUPER-SECRET-HA-TOKEN"

    async def states(self):
        return [
            {
                "entity_id": "light.kitchen",
                "state": "off",
                "attributes": {"friendly_name": "Kitchen Light"},
            }
        ]

    async def state(self, entity_id):
        return {
            "entity_id": entity_id,
            "state": "off",
            "attributes": {"friendly_name": "Kitchen Light"},
        }

    async def invoke(self, domain, service, entity_id, parameters):
        return None


@pytest.mark.asyncio
async def test_router_capability_span_is_child_correlated_and_secret_free():
    from router.ha_capability import HomeAssistantCapabilityPort

    obs = RecordingObservability()
    capability = HomeAssistantCapabilityPort(Client(), observability=obs)
    parent = new_span_id("SKILLS", "execute")
    corr = CapabilityCorrelation(
        request_id=new_request_id(),
        origin_request_id=new_request_id(),
        trace_id=new_trace_id(),
        parent_span_id=parent,
    )

    resolved = await capability.resolve(
        ResourceReference(
            reference="kitchen light",
            resource_type=NyraResourceType.LIGHT,
        ),
        {},
        correlation=corr,
    )
    assert resolved.status.value == "RESOLVED"

    executed = await capability.execute(
        ExecuteRequest(
            correlation=corr,
            operation=NyraOperation.TURN_ON,
            resource_id="light.kitchen",
            resource_type=NyraResourceType.LIGHT,
        ),
        {},
    )
    assert executed.outcome.value == "SUCCESS"

    operations = [record.operation for record in obs.records]
    assert "ha.resolve" in operations
    assert "ha.execute" in operations
    assert all(record.trace_id == corr.trace_id for record in obs.records)
    assert all(record.parent_span_id == parent for record in obs.records)
    assert len({record.span_id for record in obs.records}) == len(obs.records)

    serialized = json.dumps(
        [record.model_dump(mode="json") for record in obs.records]
    )
    assert "SUPER-SECRET-HA-TOKEN" not in serialized
    assert "Authorization" not in serialized
    assert "Bearer" not in serialized


def test_protected_skills_map_to_using_tool_and_local_skills_remain_local():
    from router.lifecycle.service import skill_interaction_state
    from shared.protocol.events import InteractionState

    assert skill_interaction_state("identity_query") is InteractionState.PROCESSING_LOCAL
    assert skill_interaction_state("memory_management") is InteractionState.USING_TOOL
    assert skill_interaction_state("home_assistant_action") is InteractionState.USING_TOOL
    assert skill_interaction_state("behavior") is InteractionState.USING_TOOL
    assert skill_interaction_state("delayed_action") is InteractionState.USING_TOOL
