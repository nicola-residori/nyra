from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from router.api.health import router


class MemoryHealth:
    def __init__(self, ready=True):
        self.is_ready = ready
        self.calls = 0

    async def ready(self):
        self.calls += 1
        return self.is_ready


def app(memory_client, *, router_ready=True):
    result = FastAPI()
    result.state.settings = SimpleNamespace(version="0.1.0")
    result.state.ready = router_ready
    result.state.memory_client = memory_client
    result.include_router(router)
    return result


def test_ready_reports_memory_dependency_failure_without_breaking_health():
    memory = MemoryHealth(False)
    client = TestClient(app(memory))

    ready = client.get("/ready")

    assert ready.status_code == 503
    assert ready.json()["reason"] == "MEMORY_NOT_READY"
    assert client.get("/health").status_code == 200
    assert memory.calls == 1


def test_ready_accepts_ready_memory_dependency():
    response = TestClient(app(MemoryHealth(True))).get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "READY"

