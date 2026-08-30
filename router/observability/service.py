from shared.protocol.observability import LogRecord
from router.observability.redaction import redact
class ObservabilityService:
    def __init__(self, store): self.store=store
    def ingest(self, records: list[LogRecord]):
        clean=[]
        for r in records:
            d=r.model_dump(); d["params"]=redact(d["params"]); d["payload"]=redact(d["payload"])
            clean.append(LogRecord.model_validate(d))
        self.store.insert_logs(clean); return len(clean)
