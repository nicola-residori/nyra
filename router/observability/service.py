from shared.protocol.observability import LogRecord
from router.observability.redaction import redact
from shared.protocol.ids import new_span_id, new_trace_id
from shared.protocol.observability import LogKind, LogLevel

class ObservabilityService:
    def __init__(self, store, request_store=None):
        self.store = store
        self.request_store = request_store

    def _authoritative_session_id(self, record: LogRecord) -> str | None:
        if self.request_store is None:
            return record.session_id
        correlated_request_id = record.request_id or record.origin_request_id
        if correlated_request_id is None:
            return None
        return self.request_store.get_session_id_for_request(correlated_request_id)

    def ingest(self, records: list[LogRecord]):
        clean=[]
        for r in records:
            d=r.model_dump()
            d["session_id"] = self._authoritative_session_id(r)
            d["params"]=redact(d["params"])
            d["payload"]=redact(d["payload"])
            clean.append(LogRecord.model_validate(d))
        self.store.insert_logs(clean)
        return len(clean)


    def trace_event(self, event: str, *, request_id: str, trace_id: str,
                    operation: str, origin_request_id: str | None = None,
                    result: str | None = None, params: dict | None = None,
                    ct: str = "ROUTER") -> None:
        self.ingest([LogRecord(
            ct=ct, level=LogLevel.INFO, kind=LogKind.EVENT, event=event,
            request_id=request_id, origin_request_id=origin_request_id or request_id,
            trace_id=trace_id, span_id=new_span_id("ROUTER", operation),
            operation=operation, result=result, params=params or {},
        )])

    def emit(self, event: str, *, operation: str, result: str | None = None,
             params: dict | None = None) -> None:
        self.ingest([LogRecord(
            ct="ROUTER",
            level=LogLevel.INFO,
            kind=LogKind.EVENT,
            event=event,
            trace_id=new_trace_id(),
            span_id=new_span_id("ROUTER", operation),
            operation=operation,
            result=result,
            params=params or {},
        )])
