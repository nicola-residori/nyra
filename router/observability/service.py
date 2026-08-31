from shared.protocol.observability import LogRecord
from router.observability.redaction import redact

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
