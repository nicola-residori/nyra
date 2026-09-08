from pathlib import Path
from shared.logging.client import NyraLogger
from router.observability.ids import *
from shared.protocol.observability import LogKind, LogLevel, LogRecord

def test_emit_is_nonblocking_and_context_bound(tmp_path:Path):
    l=NyraLogger('http://127.0.0.1:1','SKILLS',{'session_id':generate_session_id(),'request_id':generate_request_id(),'trace_id':generate_trace_id(),'span_id':generate_span_id('skills','execute')},spool_path=tmp_path/'spool',flush_interval=.01)
    r=l.info('SKILL_MATCH',payload={'token':'x'}); assert r.ct=='SKILLS'; l.close(); assert (tmp_path/'spool').exists(); assert '***REDACTED***' in (tmp_path/'spool').read_text()


def test_emit_record_accepts_dynamic_operation_correlation(tmp_path: Path):
    logger = NyraLogger(
        "http://127.0.0.1:1", "MEMORY", {},
        spool_path=tmp_path / "spool", flush_interval=0.01,
    )
    record = LogRecord(
        ct="MEMORY",
        level=LogLevel.INFO,
        kind=LogKind.EVENT,
        event="MEMORY_SEARCH_COMPLETED",
        request_id=generate_request_id(),
        trace_id=generate_trace_id(),
        span_id=generate_span_id("MEMORY", "search"),
        params={"count": 1},
    )

    returned = logger.emit_record(record)
    logger.close()

    assert returned == record
    assert record.trace_id in (tmp_path / "spool").read_text()
