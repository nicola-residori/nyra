from fastapi.testclient import TestClient
import pytest

from memory.app import create_app
from memory.config import MemorySettings


class TestEmbeddingProvider:
    provider_name = "test"
    model_name = "test-model"

    def prepare(self):
        return None


@pytest.fixture
def client(tmp_path):
    app = create_app(
        MemorySettings(data_root=tmp_path),
        embedding_provider=TestEmbeddingProvider(),
    )
    with TestClient(app) as test_client:
        yield test_client


def alias_payload(
    key="desk", target="light.office", *, scope="FAMILY", owner=None,
    enabled=True, idempotency_key="alias-1",
):
    return {
        "entry_type": "ALIAS",
        "scope": scope,
        "owner_user_id": owner,
        "key": key,
        "value": {"target": target},
        "enabled": enabled,
        "idempotency_key": idempotency_key,
    }


def resolve_payload(*lookups, user=None):
    return {
        "identity_user_id": user,
        "source_id": "nyra-mansarda",
        "area": "mansarda",
        "language": "it-IT",
        "timestamp": "2026-09-08T10:00:00Z",
        "lookups": [
            {"entry_type": entry_type, "key": key}
            for entry_type, key in lookups
        ],
    }


def test_create_list_get_update_and_delete_entry(client):
    created_response = client.post(
        "/v1/operational/entries", json=alias_payload()
    )
    assert created_response.status_code == 201
    created = created_response.json()

    listing = client.get(
        "/v1/operational/entries",
        params={"entry_type": "ALIAS", "scope": "FAMILY", "enabled": True},
    ).json()
    assert listing["total"] == 1
    assert listing["items"][0]["entry_id"] == created["entry_id"]
    assert client.get(
        f"/v1/operational/entries/{created['entry_id']}"
    ).json() == created

    updated_payload = alias_payload(
        target="light.study", enabled=False, idempotency_key="alias-update-1"
    )
    updated = client.put(
        f"/v1/operational/entries/{created['entry_id']}", json=updated_payload
    )
    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert updated.json()["value"]["target"] == "light.study"

    deleted = client.request(
        "DELETE",
        f"/v1/operational/entries/{created['entry_id']}",
        json={"idempotency_key": "alias-delete-1"},
    )
    assert deleted.status_code == 200
    assert deleted.json()["outcome"] == "SUCCESS"
    assert client.get(
        f"/v1/operational/entries/{created['entry_id']}"
    ).status_code == 404


def test_resolution_returns_applied_entry_revision(client):
    created = client.post(
        "/v1/operational/entries", json=alias_payload()
    ).json()

    response = client.post(
        "/v1/context/resolve", json=resolve_payload(("ALIAS", "desk"))
    )

    assert response.status_code == 200
    assert response.json()["values"] == {
        "ALIAS": {"desk": {"target": "light.office"}}
    }
    assert response.json()["applied"] == [
        {"entry_id": created["entry_id"], "revision": 1}
    ]


def test_resolution_maps_same_scope_conflict_to_409(client):
    client.post(
        "/v1/operational/entries",
        json=alias_payload(target="light.one", idempotency_key="one"),
    )
    client.post(
        "/v1/operational/entries",
        json=alias_payload(target="light.two", idempotency_key="two"),
    )

    response = client.post(
        "/v1/context/resolve", json=resolve_payload(("ALIAS", "desk"))
    )

    assert response.status_code == 409
    assert response.json()["outcome"] == "AMBIGUOUS"
    assert response.json()["conflicts"][0]["entry_type"] == "ALIAS"


def test_create_replays_same_idempotency_key_without_duplicate(client):
    first = client.post(
        "/v1/operational/entries", json=alias_payload()
    )
    replay = client.post(
        "/v1/operational/entries", json=alias_payload()
    )

    assert replay.status_code == 200
    assert replay.headers["x-idempotent-replay"] == "true"
    assert replay.json() == first.json()
    assert client.get("/v1/operational/entries").json()["total"] == 1


def test_reusing_idempotency_key_with_different_content_is_conflict(client):
    client.post("/v1/operational/entries", json=alias_payload())

    response = client.post(
        "/v1/operational/entries",
        json=alias_payload(target="light.other"),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_delete_is_idempotent_for_the_same_key(client):
    created = client.post(
        "/v1/operational/entries", json=alias_payload()
    ).json()
    path = f"/v1/operational/entries/{created['entry_id']}"
    payload = {"idempotency_key": "delete-1"}

    first = client.request("DELETE", path, json=payload)
    replay = client.request("DELETE", path, json=payload)

    assert first.status_code == replay.status_code == 200
    assert replay.headers["x-idempotent-replay"] == "true"


def test_missing_entries_and_invalid_filters_have_distinct_statuses(client):
    missing = client.get(
        "/v1/operational/entries/memop_123e4567-e89b-42d3-a456-426614174000"
    )
    invalid = client.get(
        "/v1/operational/entries", params={"entry_type": "UNKNOWN"}
    )

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"
    assert invalid.status_code == 422


def test_list_pagination_reports_total_before_page_slice(client):
    for index in range(3):
        client.post(
            "/v1/operational/entries",
            json=alias_payload(key=f"key-{index}", idempotency_key=f"entry-{index}"),
        )

    page = client.get(
        "/v1/operational/entries", params={"limit": 1, "offset": 1}
    ).json()

    assert page["total"] == 3
    assert len(page["items"]) == 1

