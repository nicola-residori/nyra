from pathlib import Path
from router.storage.sqlite import SQLiteObservabilityStore
from shared.protocol.observability import LogRecord,LogLevel,LogKind
from router.observability.ids import *

def test_wal_and_roundtrip(tmp_path:Path):
    s=SQLiteObservabilityStore(tmp_path/'x.db'); s.initialize()
    import sqlite3
    with sqlite3.connect(tmp_path/'x.db') as c: assert c.execute('PRAGMA journal_mode').fetchone()[0].lower()=='wal'
    r=LogRecord(ct='ROUTER',level=LogLevel.INFO,kind=LogKind.EVENT,event='X',session_id=generate_session_id(),request_id=generate_request_id(),trace_id=generate_trace_id(),span_id=generate_span_id('router','x'),payload={'a':[1,2]})
    s.insert_logs([r]); rows=s.query_logs({'event':'X'}); assert rows[0]['payload']=={'a':[1,2]}
