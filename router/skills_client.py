from __future__ import annotations

from typing import Any

import httpx
from pydantic import ValidationError

from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCheckResponse,
    SkillExecuteRequest,
    SkillExecuteResponse,
)


class SkillsUnavailable(RuntimeError):
    pass


class InvalidSkillsResponse(RuntimeError):
    pass


class SkillsClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.transport = transport

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                return await client.request(method, path, json=payload)
        except httpx.TransportError as exc:
            raise SkillsUnavailable(str(exc)) from exc

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise InvalidSkillsResponse("Skills returned invalid JSON") from exc

    async def check(self, request: SkillCheckRequest) -> SkillCheckResponse:
        response = await self._request(
            "POST",
            "/v1/skills/check",
            payload=request.model_dump(mode="json"),
        )
        if response.status_code != 200:
            raise SkillsUnavailable(
                f"Skills check returned HTTP {response.status_code}"
            )
        try:
            return SkillCheckResponse.model_validate(self._json(response))
        except ValidationError as exc:
            raise InvalidSkillsResponse(
                "Skills returned invalid check response"
            ) from exc

    async def execute(self, request: SkillExecuteRequest) -> SkillExecuteResponse:
        response = await self._request(
            "POST",
            "/v1/skills/execute",
            payload=request.model_dump(mode="json"),
        )
        if response.status_code != 200:
            raise SkillsUnavailable(
                f"Skills execute returned HTTP {response.status_code}"
            )
        try:
            return SkillExecuteResponse.model_validate(self._json(response))
        except ValidationError as exc:
            raise InvalidSkillsResponse(
                "Skills returned invalid execute response"
            ) from exc

    async def ready(self) -> bool:
        try:
            response = await self._request("GET", "/ready")
        except SkillsUnavailable:
            return False
        if response.status_code != 200:
            return False
        try:
            payload = self._json(response)
        except InvalidSkillsResponse:
            return False
        return isinstance(payload, dict) and payload.get("status") in {
            "ready",
            "READY",
        }
