import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from router.app import create_app
from router.config import RouterSettings
from shared.protocol.capabilities import CapabilityCorrelation, ExecuteRequest, ExecuteResponse
from shared.protocol.common import CommonOutcome
from shared.protocol.execution_common import NyraOperation, NyraResourceType
from shared.protocol.ids import new_request_id, new_trace_id


class FakeCapability:
    def __init__(self):
        self.calls = []

    async def execute(self, payload, trusted_context):
        self.calls.append((payload, trusted_context))
        return ExecuteResponse(correlation=payload.correlation, outcome=CommonOutcome.SUCCESS)


def test_execute_api_routes_typed_request(tmp_path):
    capability = FakeCapability()
    app = create_app(RouterSettings(database_path=tmp_path / "router.db"), ha_capability=capability)
    payload = {
        "request": ExecuteRequest(
            correlation=CapabilityCorrelation(request_id=new_request_id(), trace_id=new_trace_id()),
            operation=NyraOperation.TURN_ON,
            resource_id="light.kitchen",
            resource_type=NyraResourceType.LIGHT,
        ).model_dump(mode="json"),
        "trusted_context": {"allowed_resource_ids": ["light.kitchen"]},
    }
    with TestClient(app) as client:
        response = client.post("/v1/capabilities/home-assistant/execute", json=payload)
    assert response.status_code == 200
    assert response.json()["outcome"] == CommonOutcome.SUCCESS.value
    assert len(capability.calls) == 1


def test_execute_contract_forbids_native_service_and_arbitrary_url():
    base = dict(
        correlation=CapabilityCorrelation(request_id=new_request_id(), trace_id=new_trace_id()),
        operation=NyraOperation.TURN_ON,
        resource_id="light.kitchen",
        resource_type=NyraResourceType.LIGHT,
    )
    with pytest.raises(ValidationError): ExecuteRequest(**base, service="turn_on")
    with pytest.raises(ValidationError): ExecuteRequest(**base, url="http://evil")
