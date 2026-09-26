from fastapi.testclient import TestClient
from llm.app import create_app

class Service: pass

def test_health_is_live_and_ready_is_structural_without_inference():
    client=TestClient(create_app(service=Service()))
    assert client.get("/health").json()=={"status":"ok"}
    ready=client.get("/ready")
    assert ready.status_code==200
    assert ready.json()=={"status":"ready"}
