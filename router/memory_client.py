from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
from pydantic import ValidationError

from router.lifecycle.service import ContextResult, MemoryAccessError, MemoryQuery
from shared.protocol.ids import new_span_id
from shared.protocol.memory import (
    MemoryScope,
    OperationalEntryType,
    OperationalLookup,
    OperationalResolutionRequest,
    OperationalResolutionResult,
    SemanticSearchRequest,
    SemanticSearchResult,
)
from shared.protocol.requests import NyraRequest


class MemoryUnavailable(MemoryAccessError):
    pass


class InvalidMemoryResponse(MemoryAccessError):
    pass


class MemoryAmbiguous(RuntimeError):
    def __init__(self, result: OperationalResolutionResult):
        super().__init__("operational context is ambiguous")
        self.result = result


class MemoryClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 3.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.transport = transport

    @staticmethod
    def _headers(
        request: NyraRequest | None,
        trace_id: str | None,
        parent_span_id: str | None,
    ) -> dict[str, str]:
        headers: dict[str, str] = {}
        if trace_id is not None:
            headers["X-Nyra-Trace-Id"] = trace_id
        if request is not None and request.request_id is not None:
            headers["X-Nyra-Request-Id"] = request.request_id
        if request is not None and request.origin_request_id is not None:
            headers["X-Nyra-Origin-Request-Id"] = request.origin_request_id
        if parent_span_id is not None:
            headers["X-Nyra-Parent-Span-Id"] = parent_span_id
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retryable: bool = False,
    ) -> httpx.Response:
        attempts = 2 if retryable else 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=self.timeout,
                    transport=self.transport,
                ) as client:
                    response = await client.request(
                        method, path, json=payload, headers=headers
                    )
                if response.status_code in {502, 503, 504} and attempt + 1 < attempts:
                    continue
                return response
            except httpx.TransportError as exc:
                last_error = exc
                if attempt + 1 == attempts:
                    break
        raise MemoryUnavailable(str(last_error) if last_error else "Memory unavailable")

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise InvalidMemoryResponse("Memory returned invalid JSON") from exc

    async def resolve_context(
        self,
        request: NyraRequest,
        identity_user_id: str | None,
        trace_id: str,
        parent_span_id: str | None = None,
    ) -> ContextResult:
        lookup_key = request.input.text
        payload = OperationalResolutionRequest(
            identity_user_id=(
                identity_user_id if identity_user_id not in (None, "guest") else None
            ),
            source_id=request.source.id if request.source else None,
            area=request.source.area if request.source else None,
            language=request.language,
            timestamp=datetime.now(timezone.utc),
            lookups=[
                OperationalLookup(entry_type=entry_type, key=lookup_key)
                for entry_type in OperationalEntryType
            ],
        )
        response = await self._request(
            "POST",
            "/v1/context/resolve",
            payload=payload.model_dump(mode="json"),
            headers=self._headers(request, trace_id, parent_span_id),
            retryable=True,
        )
        if response.status_code not in {200, 409}:
            raise MemoryUnavailable(f"Memory context returned HTTP {response.status_code}")
        try:
            result = OperationalResolutionResult.model_validate(self._json(response))
        except ValidationError as exc:
            raise InvalidMemoryResponse("Memory returned invalid operational context") from exc
        if response.status_code == 409 or result.outcome.value == "AMBIGUOUS":
            raise MemoryAmbiguous(result)
        return ContextResult(data=result.values)

    async def resolve(
        self, request: NyraRequest, identity_user_id: str | None, trace_id: str
    ) -> ContextResult:
        return await self.resolve_context(
            request,
            identity_user_id,
            trace_id,
            new_span_id("ROUTER", "context_resolution"),
        )

    async def search(
        self,
        request: NyraRequest,
        identity_user_id: str | None,
        query: MemoryQuery,
        trace_id: str,
    ) -> dict[str, Any]:
        owner = identity_user_id if identity_user_id not in (None, "guest") else None
        scopes = [MemoryScope.FAMILY, MemoryScope.SYSTEM]
        if owner is not None:
            scopes.insert(0, MemoryScope.USER)
        payload = SemanticSearchRequest(
            query=query.query,
            scopes=scopes,
            owner_user_id=owner,
            memory_types=list(query.memory_types),
            limit=query.limit,
            minimum_similarity=query.minimum_similarity,
        )
        response = await self._request(
            "POST",
            "/v1/semantic/search",
            payload=payload.model_dump(mode="json"),
            headers=self._headers(
                request, trace_id, new_span_id("ROUTER", "memory_search")
            ),
            retryable=True,
        )
        if response.status_code != 200:
            raise MemoryUnavailable(f"Memory search returned HTTP {response.status_code}")
        try:
            result = SemanticSearchResult.model_validate(self._json(response))
        except ValidationError as exc:
            raise InvalidMemoryResponse("Memory returned invalid semantic search") from exc
        return result.model_dump(mode="json")

    async def ready(self) -> bool:
        try:
            response = await self._request("GET", "/ready", retryable=True)
        except MemoryUnavailable:
            return False
        if response.status_code != 200:
            return False
        try:
            payload = self._json(response)
        except InvalidMemoryResponse:
            return False
        return isinstance(payload, dict) and (
            payload.get("status") == "READY" or payload.get("ready") is True
        )
