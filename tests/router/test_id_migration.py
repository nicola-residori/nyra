from pathlib import Path
import re
import sqlite3

from router.observability.ids import generate_request_id, generate_session_id, generate_trace_id
from router.storage.sqlite import SQLiteObservabilityStore
from shared.protocol.observability import LogKind, LogLevel, LogRecord
from router.observability.ids import generate_span_id

PREFIXED_UUID = re.compile(r"^(ses|req|trc)_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def test_generated_correlation_ids_are_prefixed_uuid4():
    for value, prefix in [
        (generate_session_id(), "ses"),
        (generate_request_id(), "req"),
        (generate_trace_id(), "trc"),
    ]:
        assert value.startswith(prefix + "_")
        assert PREFIXED_UUID.fullmatch(value)


def test_job_log_allows_null_session_and_request(tmp_path: Path):
    store = SQLiteObservabilityStore(tmp_path / "logs.db")
    store.initialize()
    record = LogRecord(
        ct="ROUTER",
        level=LogLevel.INFO,
        kind=LogKind.EVENT,
        event="JOB_STARTED",
        session_id=None,
        request_id=None,
        trace_id=generate_trace_id(),
        span_id=generate_span_id("router", "job"),
    )
    store.insert_logs([record])
    row = store.query_logs({"event": "JOB_STARTED"})[0]
    assert row["session_id"] is None
    assert row["request_id"] is None


def test_initialize_migrates_legacy_not_null_log_columns_without_data_loss(tmp_path: Path):
    db = tmp_path / "legacy.db"
    with sqlite3.connect(db) as conn:
        conn.execute("""CREATE TABLE logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schema_version INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            ct TEXT NOT NULL, level TEXT NOT NULL, kind TEXT NOT NULL, event TEXT NOT NULL,
            session_id TEXT NOT NULL, request_id TEXT NOT NULL, trace_id TEXT NOT NULL, span_id TEXT NOT NULL,
            parent_span_id TEXT, origin_request_id TEXT, operation TEXT, result TEXT, message TEXT,
            session_elapsed_ms REAL, request_elapsed_ms REAL, trace_elapsed_ms REAL, span_elapsed_ms REAL,
            params_json TEXT NOT NULL, payload_json TEXT
        )""")
        conn.execute("""INSERT INTO logs(schema_version,timestamp,ct,level,kind,event,session_id,request_id,trace_id,span_id,params_json)
                      VALUES(1,'2026-08-30T20:00:00Z','ROUTER','INFO','EVENT','OLD','ses_legacy','req_legacy','trc_legacy','ROUTER#old#ABCDEFGH','{}')""")
    store = SQLiteObservabilityStore(db)
    store.initialize()
    with sqlite3.connect(db) as conn:
        cols = {row[1]: row[3] for row in conn.execute("PRAGMA table_info(logs)")}
        assert cols["session_id"] == 0
        assert cols["request_id"] == 0
        assert conn.execute("SELECT event FROM logs").fetchone()[0] == "OLD"


def test_job_logs_do_not_create_null_request_or_session_summaries(tmp_path: Path):
    store = SQLiteObservabilityStore(tmp_path / "logs.db")
    store.initialize()
    store.insert_logs([LogRecord(ct="ROUTER", level=LogLevel.INFO, kind=LogKind.EVENT, event="JOB_STARTED",
        session_id=None, request_id=None, trace_id=generate_trace_id(), span_id=generate_span_id("router","job"))])
    assert store.list_requests() == []
    assert store.list_sessions() == []
    assert len(store.list_traces()) == 1
