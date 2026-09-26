import httpx
from fastapi.testclient import TestClient
from admin.app import create_app
from admin.config import AdminSettings
from admin.client import RouterClient

def test_admin_llm_page_fetches_router_only_and_renders_fields():
    calls=[]
    async def handler(req):
        calls.append(req.url.path)
        if req.url.path=="/v1/admin/llm/diagnostics":
            return httpx.Response(200,json={"items":[{"purpose":"REASONING","outcome":"COMPLETED","provider":"openai","model":"m","latency_ms":12,"input_tokens":3,"output_tokens":2,"fallback":False,"cost":None,"capabilities":["READ_STATE"],"error_code":None}]})
        return httpx.Response(200,json=[])
    app=create_app(AdminSettings(),RouterClient("http://router",transport=httpx.MockTransport(handler)))
    with TestClient(app) as c:
        body=c.get("/llm").text
    assert "/v1/admin/llm/diagnostics" in calls
    for token in ["REASONING","COMPLETED","openai","READ_STATE"]:
        assert token in body
