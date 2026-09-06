from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi.testclient import TestClient


APP_PATH = Path(__file__).parents[2] / "speaker-id" / "app.py"


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
    app = module.create_app(data_root=tmp_path)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_ready_reports_initialized_storage(tmp_path):
    module = load_module()
    app = module.create_app(data_root=tmp_path)

    with TestClient(app) as client:
        body = client.get("/ready").json()

    assert body["ready"] is True
    assert body["storage"] == "initialized"
    assert body["model"] == "not_loaded"
