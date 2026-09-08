from fastapi.testclient import TestClient
import pytest

from memory.app import create_app
from memory.config import MemorySettings
from memory.embeddings import EmbeddingVector


TRACE_ID = "trc_123e4567-e89b-42d3-a456-426614174001"


class VectorProvider:
    provider_name = "fake"
    model_name = "fake-v1"

    def prepare(self):
        return None

    def embed(self, text):
        vectors = {
            "I prefer espresso": (1.0, 0.0),
            "I prefer tea": (0.8, 0.6),
            "coffee": (1.0, 0.0),
        }
        return EmbeddingVector(vectors[text], "fake", "fake-v1")


class EventSink:
    def __init__(self):
        self.records = []

    def emit_record(self, record):
        self.records.append(record)


@pytest.fixture
def api(tmp_path):
    sink = EventSink()
    app = create_app(
        MemorySettings(data_root=tmp_path),
        embedding_provider=VectorProvider(),
        event_sink=sink,
    )
    with TestClient(app) as client:
        yield client, sink


def headers():
    return {
        "X-Nyra-Trace-Id": TRACE_ID,
        "X-Nyra-Request-Id": "req_123e4567-e89b-42d3-a456-426614174002",
        "X-Nyra-Parent-Span-Id": "ROUTER#memory_write#ABC12345",
    }


def create_payload(content="I prefer espresso", key="write-1"):
    return {
        "memory_type": "PREFERENCE",
        "scope": "USER",
        "owner_user_id": "user-nicola",
        "content": content,
        "source": "USER_EXPLICIT",
        "idempotency_key": key,
    }


def test_semantic_create_list_get_and_search(api):
    client, _ = api
    created_response = client.post(
        "/v1/semantic/memories", json=create_payload(), headers=headers()
    )
    assert created_response.status_code == 201
    created = created_response.json()["memory"]

    listing = client.get(
        "/v1/semantic/memories",
        params={"scope": "USER", "owner_user_id": "user-nicola"},
    ).json()
    assert listing["total"] == 1
    assert listing["items"][0]["memory_id"] == created["memory_id"]
    assert client.get(
        f"/v1/semantic/memories/{created['memory_id']}"
    ).json() == created

    search = client.post(
        "/v1/semantic/search",
        json={
            "query": "coffee",
            "scopes": ["USER"],
            "owner_user_id": "user-nicola",
            "minimum_similarity": 0.5,
        },
        headers=headers(),
    )
    assert search.status_code == 200
    assert search.json()["items"][0]["memory_id"] == created["memory_id"]


def test_semantic_duplicate_replays_admission_and_idempotency(api):
    client, _ = api
    first = client.post(
        "/v1/semantic/memories", json=create_payload(), headers=headers()
    )
    replay = client.post(
        "/v1/semantic/memories", json=create_payload(), headers=headers()
    )
    duplicate = client.post(
        "/v1/semantic/memories",
        json=create_payload("  i prefer espresso  ", "write-2"),
        headers=headers(),
    )

    assert replay.status_code == 200
    assert replay.headers["x-idempotent-replay"] == "true"
    assert replay.json() == first.json()
    assert duplicate.status_code == 200
    assert duplicate.json()["admission"] == "DUPLICATE"


def test_confirm_supersede_and_delete_endpoints(api):
    client, _ = api
    old = client.post(
        "/v1/semantic/memories", json=create_payload(), headers=headers()
    ).json()["memory"]

    confirmed = client.post(
        f"/v1/semantic/memories/{old['memory_id']}/confirm",
        json={"idempotency_key": "confirm-1"},
        headers=headers(),
    )
    assert confirmed.status_code == 200

    superseded = client.post(
        f"/v1/semantic/memories/{old['memory_id']}/supersede",
        json={
            "replacement": create_payload("I prefer tea", "replacement-inner"),
            "idempotency_key": "supersede-1",
        },
        headers=headers(),
    )
    assert superseded.status_code == 201
    new = superseded.json()["memory"]
    assert new["supersedes_memory_id"] == old["memory_id"]

    deleted = client.request(
        "DELETE",
        f"/v1/semantic/memories/{new['memory_id']}",
        json={"idempotency_key": "delete-1"},
        headers=headers(),
    )
    assert deleted.status_code == 200
    assert deleted.json()["state"] == "DELETED"
    assert set(deleted.json()) == {
        "memory_id", "state", "deleted_at", "deletion_trace_id"
    }


def test_semantic_api_maps_domain_failures(api):
    client, _ = api
    missing_id = "mem_123e4567-e89b-42d3-a456-426614174000"

    missing = client.get(f"/v1/semantic/memories/{missing_id}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "NOT_FOUND"

    client.post("/v1/semantic/memories", json=create_payload(), headers=headers())
    conflict = client.post(
        "/v1/semantic/memories",
        json=create_payload("I prefer tea", "write-1"),
        headers=headers(),
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

