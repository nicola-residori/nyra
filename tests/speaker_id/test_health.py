from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient


APP_PATH = Path(__file__).parents[2] / "speaker-id" / "app.py"


class ReadyEngine:
    def load(self):
        return self


class BrokenEngine:
    def load(self):
        raise RuntimeError("model unavailable")


def load_module():
    spec = importlib.util.spec_from_file_location("nyra_speaker_id_app", APP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {APP_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_health_is_liveness(tmp_path):
    module = load_module()
    app = module.create_app(data_root=tmp_path, embedding_engine=BrokenEngine())

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_ready_requires_initialized_storage_and_loaded_model(tmp_path):
    module = load_module()
    app = module.create_app(data_root=tmp_path, embedding_engine=ReadyEngine())

    with TestClient(app) as client:
        response = client.get("/ready")
        body = response.json()

    assert response.status_code == 200
    assert body["ready"] is True
    assert body["storage"] == "initialized"
    assert body["model"] == "loaded"


def test_ready_returns_503_when_model_cannot_load(tmp_path):
    module = load_module()
    app = module.create_app(data_root=tmp_path, embedding_engine=BrokenEngine())

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "ready": False,
        "storage": "initialized",
        "model": "unavailable",
    }


def test_wake_word_sample_count_is_exposed_for_router(tmp_path):
    module = load_module()
    app = module.create_app(data_root=tmp_path, embedding_engine=ReadyEngine())

    with TestClient(app) as client:
        response = client.get("/v1/wake-word-samples/count", params={"wake_word_text": "Nyra"})

    assert response.status_code == 200
    assert response.json() == {"wake_word_text": "Nyra", "sample_count": 0}
