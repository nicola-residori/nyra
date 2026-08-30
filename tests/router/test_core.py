from pathlib import Path
from fastapi.testclient import TestClient
from router.observability.ids import *
from router.observability.redaction import redact
from router.config import RouterSettings
from router.app import create_app
import re

def sample():
    return {"schema_version":1,"ct":"ROUTER","level":"INFO","kind":"REQUEST","event":"REQUEST_RECEIVED","session_id":generate_session_id(),"request_id":generate_request_id(),"trace_id":generate_trace_id(),"span_id":generate_span_id("router","request ingress"),"params":{"token":"abc","x":1},"payload":{"authorization":"Bearer z","text":"hello"}}

def test_ids_and_redaction():
    assert generate_session_id().startswith('ses_'); assert generate_request_id().startswith('req_'); assert generate_trace_id().startswith('trc_')
    assert re.fullmatch(r"ROUTER#request_ingress#[A-Z0-9]{8}",generate_span_id('router','request ingress'))
    src={"Token":"x","nested":[{"password":"y","ok":1}]}; out=redact(src); assert out["Token"]=='***REDACTED***'; assert out["nested"][0]["password"]=='***REDACTED***'; assert src["Token"]=='x'

def test_health_ingest_query_and_redaction(tmp_path:Path):
    app=create_app(RouterSettings(database_path=tmp_path/'logs.db'))
    with TestClient(app) as c:
        assert c.get('/health').json()['status']=='healthy'
        rec=sample(); assert c.post('/v1/logs/ingest',json={'records':[rec]}).json()['accepted']==1
        rows=c.get('/v1/logs',params={'trace_id':rec['trace_id']}).json(); assert len(rows)==1; assert rows[0]['params']['token']=='***REDACTED***'; assert rows[0]['payload']['authorization']=='***REDACTED***'
        assert c.get('/v1/traces/'+rec['trace_id']).status_code==200

def test_invalid_batch_atomic(tmp_path:Path):
    app=create_app(RouterSettings(database_path=tmp_path/'logs.db'))
    good=sample(); bad={**sample(),"kind":"BAD"}
    with TestClient(app) as c:
        assert c.post('/v1/logs/ingest',json={'records':[good,bad]}).status_code==422
        assert c.get('/v1/logs').json()==[]
