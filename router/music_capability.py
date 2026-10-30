"""Router-owned authenticated gateway; Skills never holds HA credentials."""

import httpx


class MusicCapability:
    def __init__(self, base_url, token, *, transport=None):
        self.base_url = base_url
        self.token = token
        self.transport = transport

    async def music(self, payload):
        if not self.base_url or not self.token:
            return {
                "status": "ERROR",
                "text": "Il servizio musicale non è configurato.",
            }
        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=12,
            transport=self.transport,
        ) as client:
            response = await client.post(
                "/api/nyra/music", json=payload.model_dump(mode="json")
            )
            response.raise_for_status()
            return response.json()
