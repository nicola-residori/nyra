from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from router.api.health import router


def app(ready: bool) -> FastAPI:
    result = FastAPI()
    result.state.settings = SimpleNamespace(version="0.1.0")
    result.state.ready = ready
    result.include_router(router)
    return result


def test_health_uses_shared_service_contract():
    response = TestClient(app(True)).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "HEALTHY", "service": "nyra-router", "version": "0.1.0", "reason": None}


def test_ready_reflects_router_foundation_readiness():
    assert TestClient(app(True)).get("/ready").json()["status"] == "READY"
    not_ready = TestClient(app(False)).get("/ready")
    assert not_ready.status_code == 503
    assert not_ready.json()["status"] == "NOT_READY"
