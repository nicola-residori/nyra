import httpx
import pytest

from homeassistant.custom_components.nyra.client import (
    NyraRouterClient,
    NyraRouterInvalidResponse,
    NyraRouterRejected,
    NyraRouterUnavailable,
)
from homeassistant.custom_components.nyra.const import REQUEST_PATH
from shared.protocol.ids import new_request_id, new_session_id, new_trace_id
from shared.protocol.requests import NyraRequest


def req():
    return NyraRequest.model_validate({
        "type":"ha_assist", "session_id":new_session_id(), "request_id":new_request_id(),
        "language":"it", "source":{"id":"ha"}, "identity":{"user_id":"u","provider":"home_assistant","confidence":1},
        "input":{"text":"ciao"}
    })


@pytest.mark.asyncio
async def test_ready_uses_ready_contract():
    async def handler(request):
        assert request.url.path == "/ready"
        return httpx.Response(200, json={"service":"nyra-router","status":"READY","version":"0.1.0","reason":None})
    client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert await NyraRouterClient("http://router:8090", client=client).async_ready()
    await client.aclose()


@pytest.mark.asyncio
async def test_execute_posts_once_to_existing_router_endpoint_with_token():
    calls=[]
    async def handler(request):
        calls.append(request)
        assert request.url.path == REQUEST_PATH
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(200,json={"status":"completed","session_id":req_obj.session_id,"request_id":req_obj.request_id,"trace_id":new_trace_id(),"response":{"text":"Fatto."}})
    req_obj=req()
    raw=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result=await NyraRouterClient("http://router:8090/", "secret", client=raw).async_execute(req_obj)
    assert result.response.text == "Fatto." and len(calls)==1
    await raw.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,exc", [(409,NyraRouterRejected),(500,NyraRouterUnavailable)])
async def test_execute_maps_http_failures_without_retry(status,exc):
    calls=0
    async def handler(request):
        nonlocal calls; calls += 1
        return httpx.Response(status,json={"detail":"x"})
    raw=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(exc):
        await NyraRouterClient("http://router:8090", client=raw).async_execute(req())
    assert calls == 1
    await raw.aclose()


@pytest.mark.asyncio
async def test_invalid_payload_is_rejected():
    raw=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={"oops":True})))
    with pytest.raises(NyraRouterInvalidResponse):
        await NyraRouterClient("http://router:8090", client=raw).async_execute(req())
    await raw.aclose()
