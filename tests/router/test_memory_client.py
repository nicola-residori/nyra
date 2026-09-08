from __future__ import annotations

import httpx
import pytest

from router.memory_client import (
    InvalidMemoryResponse,
    MemoryAmbiguous,
    MemoryClient,
    MemoryUnavailable,
)
from shared.protocol.ids import new_request_id, new_session_id, new_span_id, new_trace_id
from shared.protocol.requests import NyraRequest


def nyra_request(text: str = "scrivania") -> NyraRequest:
    return NyraRequest.model_validate({
        "type": "ha_speaker",
        "session_id": new_session_id(),
        "request_id": new_request_id(),
        "language": "it-IT",
        "source": {"id": "nyra-mansarda", "area": "mansarda"},
        "input": {"text": text},
    })


@pytest.mark.asyncio
async def test_context_client_forwards_correlation_and_trusted_identity():
    seen = []

    async def handler(request: httpx.Request):
        seen.append(request)
        return httpx.Response(200, json={
            "outcome": "SUCCESS",
            "values": {"ALIAS": {"scrivania": {"target": "light.office"}}},
            "applied": [],
            "conflicts": [],
        })

    client = MemoryClient(
        "http://memory.test", transport=httpx.MockTransport(handler)
    )
    trace_id = new_trace_id()
    parent_span_id = new_span_id("ROUTER", "context_resolution")
    request = nyra_request()

    result = await client.resolve_context(
        request, "user-nicola", trace_id, parent_span_id
    )

    assert result.data["ALIAS"]["scrivania"]["target"] == "light.office"
    sent = seen[0]
    assert sent.headers["x-nyra-trace-id"] == trace_id
    assert sent.headers["x-nyra-request-id"] == request.request_id
    assert sent.headers["x-nyra-parent-span-id"] == parent_span_id
    payload = __import__("json").loads(sent.content)
    assert payload["identity_user_id"] == "user-nicola"
    assert payload["source_id"] == "nyra-mansarda"
    assert payload["area"] == "mansarda"
    assert {item["entry_type"] for item in payload["lookups"]} == {
        "ALIAS", "MAPPING", "DEFAULT", "SHORTCUT"
    }


@pytest.mark.asyncio
async def test_context_conflict_is_not_silently_accepted():
    async def handler(request: httpx.Request):
        return httpx.Response(409, json={
            "outcome": "AMBIGUOUS",
            "values": {},
            "applied": [],
            "conflicts": [{
                "entry_type": "ALIAS",
                "key": "scrivania",
                "scope": "FAMILY",
                "entry_ids": [
                    "memop_123e4567-e89b-42d3-a456-426614174001",
                    "memop_123e4567-e89b-42d3-a456-426614174002",
                ],
            }],
        })

    client = MemoryClient("http://memory.test", transport=httpx.MockTransport(handler))
    with pytest.raises(MemoryAmbiguous):
        await client.resolve_context(nyra_request(), "user-nicola", new_trace_id())


@pytest.mark.asyncio
async def test_malformed_context_response_is_distinct_from_unavailability():
    async def handler(request: httpx.Request):
        return httpx.Response(200, json={"outcome": "SUCCESS", "values": "wrong"})

    client = MemoryClient("http://memory.test", transport=httpx.MockTransport(handler))
    with pytest.raises(InvalidMemoryResponse):
        await client.resolve_context(nyra_request(), "user-nicola", new_trace_id())


@pytest.mark.asyncio
async def test_idempotent_context_read_retries_once_on_transport_failure():
    calls = 0

    async def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, json={
            "outcome": "SUCCESS", "values": {}, "applied": [], "conflicts": []
        })

    client = MemoryClient("http://memory.test", transport=httpx.MockTransport(handler))
    await client.resolve_context(nyra_request(), None, new_trace_id())
    assert calls == 2


@pytest.mark.asyncio
async def test_unavailable_after_bounded_retry():
    calls = 0

    async def handler(request: httpx.Request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("slow", request=request)

    client = MemoryClient("http://memory.test", transport=httpx.MockTransport(handler))
    with pytest.raises(MemoryUnavailable):
        await client.resolve_context(nyra_request(), None, new_trace_id())
    assert calls == 2

