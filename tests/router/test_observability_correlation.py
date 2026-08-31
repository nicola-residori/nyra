from datetime import datetime, timezone
from router.lifecycle.models import PersistedRequestState
from router.lifecycle.store import RequestStateStore
from router.observability.service import ObservabilityService
from router.storage.sqlite import SQLiteObservabilityStore
from shared.protocol.ids import new_request_id, new_session_id, new_span_id, new_trace_id
from shared.protocol.observability import LogKind, LogLevel, LogRecord
from shared.protocol.requests import ExecutionType, RequestStatus


def test_distributed_logs_are_enriched_from_request_mapping(tmp_path):
    db=tmp_path/"router.db"; requests=RequestStateStore(db); requests.initialize(); logs=SQLiteObservabilityStore(db); logs.initialize()
    session_id=new_session_id(); request_id=new_request_id(); trace=new_trace_id(); now=datetime.now(timezone.utc)
    requests.create(PersistedRequestState(request_id=request_id,session_id=session_id,type=ExecutionType.HA_ASSIST,language="it",original_input="x",status=RequestStatus.COMPLETED,current_trace_id=trace,created_at=now,updated_at=now))
    svc=ObservabilityService(logs, request_store=requests)
    records=[
      LogRecord(ct="SKILLS",level=LogLevel.INFO,kind=LogKind.EVENT,event="MATCH",request_id=request_id,trace_id=new_trace_id(),span_id=new_span_id("SKILLS","match")),
      LogRecord(ct="SKILLS",level=LogLevel.INFO,kind=LogKind.EVENT,event="JOB",origin_request_id=request_id,trace_id=new_trace_id(),span_id=new_span_id("SKILLS","job")),
      LogRecord(ct="SKILLS",level=LogLevel.INFO,kind=LogKind.EVENT,event="WRONG",session_id=new_session_id(),request_id=request_id,trace_id=new_trace_id(),span_id=new_span_id("SKILLS","wrong")),
    ]
    svc.ingest(records)
    rows=logs.get_session(session_id)["logs"]
    assert len(rows)==3
    assert all(row["session_id"]==session_id for row in rows)
    assert {row["event"] for row in rows}=={"MATCH","JOB","WRONG"}
    assert next(row for row in rows if row["event"]=="JOB")["origin_request_id"]==request_id
