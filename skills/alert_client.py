"""Router-only client for deferred audio."""

import httpx
from shared.protocol.alerts import AlertResponse


class RouterAlertClient:
    def __init__(self, base_url, *, timeout=3.0, transport=None):
        self.base_url = base_url
        self.timeout = timeout
        self.transport = transport

    async def alert(self, request):
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, transport=self.transport
        ) as client:
            response = await client.post(
                "/v1/capabilities/audio", json=request.model_dump(mode="json")
            )
            response.raise_for_status()
            return AlertResponse.model_validate(response.json())
