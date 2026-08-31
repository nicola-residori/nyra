from __future__ import annotations

import httpx

from shared.protocol.requests import NyraRequest, NyraRequestResponse
from shared.protocol.service import ServiceState, ServiceStatusResponse

from .const import DEFAULT_TIMEOUT_SECONDS, READY_PATH, REQUEST_PATH


class NyraRouterError(RuntimeError):
    pass


class NyraRouterUnavailable(NyraRouterError):
    pass


class NyraRouterRejected(NyraRouterError):
    pass


class NyraRouterInvalidResponse(NyraRouterError):
    pass


class NyraRouterClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token or None
        self.timeout = timeout
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    async def async_ready(self) -> bool:
        try:
            response = await self._client.get(
                f"{self.base_url}{READY_PATH}", headers=self.headers, timeout=self.timeout
            )
            response.raise_for_status()
            status = ServiceStatusResponse.model_validate(response.json())
            return status.status is ServiceState.READY
        except (httpx.HTTPError, ValueError):
            return False

    async def async_execute(self, request: NyraRequest) -> NyraRequestResponse:
        try:
            response = await self._client.post(
                f"{self.base_url}{REQUEST_PATH}",
                headers=self.headers,
                json=request.model_dump(mode="json"),
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise NyraRouterUnavailable("Nyra Router is unavailable") from exc

        if 400 <= response.status_code < 500:
            raise NyraRouterRejected(f"Router rejected request with HTTP {response.status_code}")
        if response.status_code >= 500:
            raise NyraRouterUnavailable(f"Router failed with HTTP {response.status_code}")
        try:
            response.raise_for_status()
            return NyraRequestResponse.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise NyraRouterInvalidResponse("Router returned an invalid response") from exc

    async def async_close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
