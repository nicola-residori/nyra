from __future__ import annotations

from time import monotonic

from shared.protocol.ids import CorrelationContext, new_span_id, new_trace_id
from shared.protocol.observability import LogKind, LogLevel, LogRecord


def correlation_from_headers(headers) -> CorrelationContext:
    return CorrelationContext(
        request_id=headers.get("x-nyra-request-id"),
        origin_request_id=headers.get("x-nyra-origin-request-id"),
        trace_id=headers.get("x-nyra-trace-id") or new_trace_id(),
        parent_span_id=headers.get("x-nyra-parent-span-id"),
    )


class MemoryObservability:
    def __init__(self, event_sink=None):
        self.event_sink = event_sink

    def emit(
        self,
        event: str,
        operation: str,
        correlation: CorrelationContext,
        *,
        result: str | None = None,
        params: dict | None = None,
        started_at: float | None = None,
        fault: bool = False,
        span_id: str | None = None,
    ) -> LogRecord:
        elapsed = None
        if started_at is not None:
            elapsed = round((monotonic() - started_at) * 1000, 3)
        record = LogRecord(
            ct="MEMORY",
            level=LogLevel.ERROR if fault else LogLevel.INFO,
            kind=LogKind.FAULT if fault else LogKind.EVENT,
            event=event,
            request_id=correlation.request_id,
            origin_request_id=correlation.origin_request_id,
            trace_id=correlation.trace_id,
            span_id=span_id or new_span_id("MEMORY", operation),
            parent_span_id=correlation.parent_span_id,
            operation=operation,
            result=result,
            span_elapsed_ms=elapsed,
            params=params or {},
        )
        if self.event_sink is not None:
            self.event_sink.emit_record(record)
        return record
