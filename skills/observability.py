from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from shared.protocol.ids import new_span_id
from shared.protocol.observability import LogKind, LogLevel, LogRecord


class RouterObservabilityClient:
    """Sends Skills spans to the Router's existing centralized log ingest API."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 3.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.transport = transport

    def ingest(self, record: LogRecord) -> None:
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout,
                transport=self.transport,
            ) as client:
                response = client.post(
                    "/v1/logs/ingest",
                    json=record.model_dump(mode="json"),
                )
                response.raise_for_status()
        except httpx.HTTPError:
            # Observability must never break deterministic execution.
            return


class SkillsObservability:
    def __init__(
        self,
        sink: Callable[[LogRecord], None] | None = None,
    ) -> None:
        self.sink = sink

    def span(
        self,
        operation: str,
        correlation,
        *,
        event: str | None = None,
        result: str | None = None,
        parent_span_id: str | None = None,
        params: dict[str, Any] | None = None,
        kind: LogKind = LogKind.EVENT,
    ) -> str:
        span_id = new_span_id("SKILLS", operation)
        record = LogRecord(
            ct="SKILLS",
            level=LogLevel.INFO,
            kind=kind,
            event=event or operation,
            request_id=correlation.request_id,
            origin_request_id=correlation.origin_request_id,
            trace_id=correlation.trace_id,
            span_id=span_id,
            parent_span_id=(
                parent_span_id
                if parent_span_id is not None
                else correlation.parent_span_id
            ),
            operation=operation,
            result=result,
            params=dict(params or {}),
        )
        if self.sink is not None:
            self.sink(record)
        return span_id
