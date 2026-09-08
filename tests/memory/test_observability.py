import json

from fastapi.testclient import TestClient

from memory.app import create_app
from memory.config import MemorySettings
from memory.embeddings import EmbeddingVector


class Provider:
    provider_name = "fake"
    model_name = "fake-v1"

    def prepare(self):
        return None

    def embed(self, text):
        return EmbeddingVector((1.0, 0.0), "fake", "fake-v1")


class Sink:
    def __init__(self):
        self.records = []

    def emit_record(self, record):
        self.records.append(record)


def test_semantic_operations_log_correlation_without_content(tmp_path):
    sink = Sink()
    app = create_app(
        MemorySettings(data_root=tmp_path),
        embedding_provider=Provider(),
        event_sink=sink,
    )
    trace_id = "trc_123e4567-e89b-42d3-a456-426614174001"
    request_id = "req_123e4567-e89b-42d3-a456-426614174002"
    headers = {
        "X-Nyra-Trace-Id": trace_id,
        "X-Nyra-Request-Id": request_id,
        "X-Nyra-Parent-Span-Id": "ROUTER#memory_search#ABC12345",
    }

    with TestClient(app) as client:
        client.post(
            "/v1/semantic/memories",
            json={
                "memory_type": "PREFERENCE",
                "scope": "USER",
                "owner_user_id": "user-nicola",
                "content": "secret espresso preference",
                "source": "USER_EXPLICIT",
                "idempotency_key": "write-1",
            },
            headers=headers,
        )
        client.post(
            "/v1/semantic/search",
            json={
                "query": "secret espresso preference",
                "scopes": ["USER"],
                "owner_user_id": "user-nicola",
            },
            headers=headers,
        )

    completed = [
        record for record in sink.records
        if record.event in {"MEMORY_WRITE_COMPLETED", "MEMORY_SEARCH_COMPLETED"}
    ]
    assert len(completed) == 2
    assert all(record.ct == "MEMORY" for record in completed)
    assert all(record.trace_id == trace_id for record in completed)
    assert all(record.request_id == request_id for record in completed)
    assert all(record.parent_span_id == headers["X-Nyra-Parent-Span-Id"] for record in completed)
    serialized = json.dumps([record.model_dump(mode="json") for record in sink.records])
    assert "secret espresso preference" not in serialized
    assert "embedding" not in serialized.casefold()

    search_events = [
        record.event for record in sink.records
        if record.operation == "memory_search"
    ]
    assert search_events == ["MEMORY_SEARCH_START", "MEMORY_SEARCH_COMPLETED"]
    search_records = [
        record for record in sink.records if record.operation == "memory_search"
    ]
    assert len({record.span_id for record in search_records}) == 1


def test_operational_resolution_emits_correlated_start_and_completion(tmp_path):
    sink = Sink()
    app = create_app(
        MemorySettings(data_root=tmp_path),
        embedding_provider=Provider(),
        event_sink=sink,
    )
    headers = {
        "X-Nyra-Trace-Id": "trc_123e4567-e89b-42d3-a456-426614174001",
        "X-Nyra-Request-Id": "req_123e4567-e89b-42d3-a456-426614174002",
    }
    with TestClient(app) as client:
        client.post(
            "/v1/context/resolve",
            json={
                "source_id": "nyra-mansarda",
                "area": "mansarda",
                "language": "it-IT",
                "timestamp": "2026-09-08T10:00:00Z",
                "lookups": [{"entry_type": "ALIAS", "key": "desk"}],
            },
            headers=headers,
        )

    events = [record for record in sink.records if record.operation == "context_resolution"]
    assert [record.event for record in events] == [
        "CONTEXT_RESOLUTION_START", "CONTEXT_RESOLUTION_COMPLETED"
    ]
    assert events[-1].result == "SUCCESS"
    assert events[-1].params == {"applied_count": 0, "conflict_count": 0}
    assert events[0].span_id == events[1].span_id


def test_failed_operation_emits_fault_without_sensitive_payload(tmp_path):
    sink = Sink()
    app = create_app(
        MemorySettings(data_root=tmp_path),
        embedding_provider=Provider(),
        event_sink=sink,
    )
    headers = {
        "X-Nyra-Trace-Id": "trc_123e4567-e89b-42d3-a456-426614174001"
    }

    with TestClient(app) as client:
        response = client.get(
            "/v1/semantic/memories/mem_123e4567-e89b-42d3-a456-426614174000",
            headers=headers,
        )

    assert response.status_code == 404
    fault = sink.records[-1]
    assert fault.kind.value == "FAULT"
    assert fault.result == "NOT_FOUND"
    assert fault.payload is None
