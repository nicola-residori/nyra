"""Router-owned authenticated HA audio gateway."""

import httpx
from shared.protocol.alerts import AlertResponse, AlertState


class AlertCapability:
    def __init__(self, base_url, token, *, timeout=3.0, transport=None):
        self.base_url = base_url
        self.token = token
        self.timeout = timeout
        self.transport = transport

    async def alert(self, request):
        if not self.base_url or not self.token:
            return AlertResponse(state=AlertState.OFFLINE, error="HA_NOT_CONFIGURED")
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            transport=self.transport,
            headers={"Authorization": f"Bearer {self.token}"},
        ) as client:
            response = await client.post(
                "/api/nyra/alerts", json=request.model_dump(mode="json")
            )
            response.raise_for_status()
            return AlertResponse.model_validate(response.json())
