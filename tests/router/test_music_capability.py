import httpx
import pytest
from shared.protocol.music import MusicRequest
from shared.protocol.ids import new_request_id, new_trace_id


@pytest.mark.asyncio
async def test_music_router_uses_authenticated_ha_adapter_and_typed_payload():
    from router.music_capability import MusicCapability

    rid = new_request_id()
    request = MusicRequest(
        source_id="speaker",
        session_id="session",
        correlation={
            "request_id": rid,
            "origin_request_id": rid,
            "trace_id": new_trace_id(),
        },
        command={"action": "PAUSE"},
    )

    def handle(req):
        assert req.url.path == "/api/nyra/music"
        assert req.headers["Authorization"] == "Bearer secret"
        assert b"PAUSE" in req.content
        return httpx.Response(200, json={"status": "OK", "text": "Fatto."})

    result = await MusicCapability(
        "http://ha", "secret", transport=httpx.MockTransport(handle)
    ).music(request)
    assert result["status"] == "OK"
    assert (await MusicCapability(None, None).music(request))["status"] == "ERROR"
