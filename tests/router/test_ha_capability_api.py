from __future__ import annotations

from fastapi.testclient import TestClient

from router.app import create_app
from router.config import RouterSettings
from shared.protocol.capabilities import (
    CapabilityCorrelation,
    ResolveResponse,
    ResolveStatus,
    ResourceReference,
)
from shared.protocol.ids import new_request_id, new_trace_id


class FakeCapability:
    def __init__(self):
        self.calls = []

    async def resolve(self, reference, trusted_context, correlation):
        self.calls.append((reference, trusted_context, correlation))
        return ResolveResponse(
            correlation=correlation,
            status=ResolveStatus.NOT_FOUND,
            reference=reference,
            candidates=[],
        )


def test_capability_resolve_api_uses_router_owned_capability_and_trusted_context(tmp_path):
    capability = FakeCapability()
    app = create_app(
        RouterSettings(database_path=tmp_path / "router.db"),
        ha_capability=capability,
    )

    payload = {
        "correlation": CapabilityCorrelation(
            request_id=new_request_id(),
            trace_id=new_trace_id(),
        ).model_dump(mode="json"),
        "reference": ResourceReference(
            reference="kitchen light",
        ).model_dump(mode="json"),
        "trusted_context": {
            "allowed_resource_ids": ["light.kitchen"],
        },
    }

    with TestClient(app) as client:
        response = client.post(
            "/v1/capabilities/home-assistant/resolve",
            json=payload,
        )

    assert response.status_code == 200
    assert response.json()["status"] == ResolveStatus.NOT_FOUND.value
    assert len(capability.calls) == 1
    reference, trusted_context, correlation = capability.calls[0]
    assert reference.reference == "kitchen light"
    assert trusted_context == {"allowed_resource_ids": ["light.kitchen"]}
    assert correlation.request_id == payload["correlation"]["request_id"]


def test_capability_api_never_accepts_home_assistant_credentials_in_request(tmp_path):
    capability = FakeCapability()
    app = create_app(
        RouterSettings(database_path=tmp_path / "router.db"),
        ha_capability=capability,
    )

    payload = {
        "correlation": {
            "request_id": new_request_id(),
            "trace_id": new_trace_id(),
        },
        "reference": {"reference": "kitchen light"},
        "trusted_context": {},
        "home_assistant_token": "must-not-cross-boundary",
    }

    with TestClient(app) as client:
        response = client.post(
            "/v1/capabilities/home-assistant/resolve",
            json=payload,
        )

    assert response.status_code == 422
    assert capability.calls == []
