from __future__ import annotations

import dataclasses
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


def test_identification_config_has_bootstrap_defaults_and_revision(tmp_path):
    module = load_module()
    app = module.create_app(data_root=tmp_path)

    with TestClient(app) as client:
        response = client.get("/v1/config")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == 1
    assert body["identification"] == {
        "threshold": 0.40,
        "margin": 0.07,
        "revision": 1,
    }


def test_identification_config_persists_across_app_restart(tmp_path):
    module = load_module()

    first_app = module.create_app(data_root=tmp_path)
    with TestClient(first_app) as client:
        response = client.put(
            "/v1/config/identification",
            json={"threshold": 0.43, "margin": 0.09},
        )
        assert response.status_code == 200
        assert response.json() == {
            "threshold": 0.43,
            "margin": 0.09,
            "revision": 2,
        }

    restarted_app = module.create_app(data_root=tmp_path)
    with TestClient(restarted_app) as client:
        body = client.get("/v1/config").json()

    assert body["identification"] == {
        "threshold": 0.43,
        "margin": 0.09,
        "revision": 2,
    }


def test_identification_snapshot_is_immutable_and_revisioned(tmp_path):
    module = load_module()
    app = module.create_app(data_root=tmp_path)

    with TestClient(app) as client:
        before = app.state.config_store.identification_snapshot()
        client.put(
            "/v1/config/identification",
            json={"threshold": 0.45, "margin": 0.10},
        )
        after = app.state.config_store.identification_snapshot()

    assert isinstance(before, module.IdentificationConfigSnapshot)
    assert dataclasses.is_dataclass(before)
    assert before.threshold == 0.40
    assert before.margin == 0.07
    assert before.revision == 1
    assert after.threshold == 0.45
    assert after.margin == 0.10
    assert after.revision == 2

    try:
        before.threshold = 0.99
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("IdentificationConfigSnapshot must be immutable")
