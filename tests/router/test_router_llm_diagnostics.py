from fastapi.testclient import TestClient
from router.app import create_app
from router.config import RouterSettings

def test_router_exposes_sanitized_llm_diagnostics(tmp_path):
    app=create_app(RouterSettings(database_path=str(tmp_path/"r.sqlite3")))
    app.state.llm_diagnostics=[{"request_id":"req_x","trace_id":"trc_x","reasoning_id":"reason_1","purpose":"REASONING","outcome":"COMPLETED","provider":"p","model":"m","latency_ms":1.2,"input_tokens":3,"output_tokens":2,"fallback":False,"cost":None,"capabilities":["READ_STATE"],"error_code":None}]
    with TestClient(app) as c:
        data=c.get("/v1/admin/llm/diagnostics").json()
    assert data["items"][0]["cost"] is None
    assert "prompt" not in str(data).lower()
