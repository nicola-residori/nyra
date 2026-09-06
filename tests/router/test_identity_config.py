from __future__ import annotations

import importlib
from fastapi.testclient import TestClient


def test_identity_timeout_config_is_persistent_and_revisioned(tmp_path):
    module = importlib.import_module("router.identity_config")
    db = tmp_path / "router.db"
    store = module.IdentityRuntimeConfigStore(db, default_timeout_seconds=1.5)
    store.initialize()
    first = store.snapshot()
    assert first.identification_timeout_seconds == 1.5
    assert first.revision == 1

    second = store.update_identification_timeout(.75)
    assert second.identification_timeout_seconds == .75
    assert second.revision == 2

    reopened = module.IdentityRuntimeConfigStore(db, default_timeout_seconds=99)
    assert reopened.snapshot() == second


def test_identity_timeout_config_api_updates_without_restart(tmp_path):
    app_module = importlib.import_module("router.app")
    config_module = importlib.import_module("router.config")
    app = app_module.create_app(config_module.RouterSettings(database_path=tmp_path / "router.db"))

    with TestClient(app) as client:
        before = client.get("/v1/config/identity")
        assert before.status_code == 200
        revision = before.json()["revision"]

        changed = client.put("/v1/config/identity", json={"identification_timeout_seconds": .4})
        assert changed.status_code == 200
        assert changed.json() == {
            "identification_timeout_seconds": .4,
            "revision": revision + 1,
        }

        after = client.get("/v1/config/identity")
        assert after.json() == changed.json()
