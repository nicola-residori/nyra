from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from router.api.health import router


class FakeReadyClient:
    def __init__(self, ready: bool):
        self._ready = ready
        self.calls = 0

    async def ready(self) -> bool:
        self.calls += 1
        return self._ready


def app(*, skills_client=None, memory_client=None) -> FastAPI:
    result = FastAPI()
    result.state.settings = SimpleNamespace(version="0.1.0")
    result.state.ready = True
    result.state.skills_client = skills_client
    result.state.memory_client = memory_client
    result.include_router(router)
    return result


def test_ready_ignores_skills_when_not_configured():
    response = TestClient(app()).get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "READY"


def test_ready_checks_skills_when_configured():
    skills = FakeReadyClient(True)

    response = TestClient(app(skills_client=skills)).get("/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "READY"
    assert skills.calls == 1


def test_ready_fails_when_configured_skills_is_not_ready():
    skills = FakeReadyClient(False)

    response = TestClient(app(skills_client=skills)).get("/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "NOT_READY"
    assert response.json()["reason"] == "SKILLS_NOT_READY"
    assert skills.calls == 1
