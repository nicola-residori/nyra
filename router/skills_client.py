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

    async def diagnostics(self) -> dict[str, Any]:
        health_response = await self._request("GET", "/health")
        if health_response.status_code != 200:
            raise SkillsUnavailable(
                f"Skills health returned HTTP {health_response.status_code}"
            )
        ready_response = await self._request("GET", "/ready")
        skills_response = await self._request("GET", "/v1/skills")
        jobs_response = await self._request("GET", "/v1/jobs")

        if skills_response.status_code != 200:
            raise SkillsUnavailable(
                f"Skills metadata returned HTTP {skills_response.status_code}"
            )
        if jobs_response.status_code != 200:
            raise SkillsUnavailable(
                f"Skills jobs returned HTTP {jobs_response.status_code}"
            )

        health = self._json(health_response)
        ready_payload = self._json(ready_response)
        skills = self._json(skills_response)
        jobs = self._json(jobs_response)
        if not isinstance(health, dict):
            raise InvalidSkillsResponse("Skills health response must be an object")
        if not isinstance(skills, list):
            raise InvalidSkillsResponse("Skills metadata response must be a list")
        if not isinstance(jobs, list):
            raise InvalidSkillsResponse("Skills jobs response must be a list")
        ready = (
            ready_response.status_code == 200
            and isinstance(ready_payload, dict)
            and ready_payload.get("status") in {"ready", "READY"}
        )
        return {
            "health": health,
            "ready": ready,
            "skills": skills,
            "jobs": jobs,
        }

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
