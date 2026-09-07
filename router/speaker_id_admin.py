from __future__ import annotations

import httpx


class SpeakerIdAdminUnavailable(RuntimeError):
    pass


class SpeakerIdAdminClient:
    def __init__(self, base_url: str | None, *, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/") if base_url else None
        self.timeout = timeout

    async def _request(self, method, path, *, params=None, payload=None):
        if self.base_url is None:
            raise SpeakerIdAdminUnavailable("Speaker-ID API is unavailable")
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
                response = await client.request(method, path, params=params, json=payload)
                response.raise_for_status()
                return response
        except httpx.HTTPError as exc:
            raise SpeakerIdAdminUnavailable(str(exc)) from exc

    async def json(self, method, path, *, params=None, payload=None):
        response = await self._request(method, path, params=params, payload=payload)
        try:
            return response.json()
        except ValueError as exc:
            raise SpeakerIdAdminUnavailable("Speaker-ID returned invalid JSON") from exc

    async def binary(self, method, path, *, payload=None):
        response = await self._request(method, path, payload=payload)
        return response.content, response.headers.get("content-type", "application/octet-stream"), response.headers.get("content-disposition")
