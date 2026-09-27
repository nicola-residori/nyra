from fastapi.testclient import TestClient
from router.app import create_app
from router.config import RouterSettings
class LlmDiagnosticsClient:
    async def diagnostics(self):
        return {"items":[{"purpose":"REASONING","outcome":"SUCCESS","provider":"openai","model":"m","latency_ms":1.2,"input_tokens":3,"output_tokens":2,"fallback":False,"cost":None,"error_code":None}]}
def test_router_proxies_live_llm_diagnostics(tmp_path):
    app=create_app(RouterSettings(database_path=tmp_path/"r.sqlite3"),llm_client=LlmDiagnosticsClient())
    with TestClient(app) as client:
        response=client.get("/v1/admin/llm/diagnostics")
    assert response.status_code==200
    data=response.json()
    assert data["items"][0]["provider"]=="openai"
    assert data["items"][0]["cost"] is None
    assert "prompt" not in str(data).lower()
