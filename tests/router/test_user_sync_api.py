from fastapi.testclient import TestClient

from router.app import create_app
from router.config import RouterSettings


def test_authenticated_user_sync_persists_reference(tmp_path):
    app = create_app(
        RouterSettings(
            database_path=tmp_path / "router.db",
            ingress_token="secret",
        ),
        audio_sink=object(),
    )
    payload = {
        "provider": "home_assistant",
        "user_id": "ha-1",
        "display_name": "  Nicola  ",
    }

    with TestClient(app) as client:
        unauthorized = client.post("/v1/users/sync", json=payload)
        accepted = client.post(
            "/v1/users/sync",
            headers={"Authorization": "Bearer secret"},
            json=payload,
        )

    assert unauthorized.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json() == {
        "provider": "home_assistant",
        "user_id": "ha-1",
        "display_name": "Nicola",
        "updated_at": accepted.json()["updated_at"],
    }
    assert app.state.user_directory.get(
        "home_assistant", "ha-1"
    ).display_name == "Nicola"


def test_user_sync_rejects_empty_or_overlong_names(tmp_path):
    app = create_app(
        RouterSettings(database_path=tmp_path / "router.db"),
        audio_sink=object(),
    )
    base = {"provider": "home_assistant", "user_id": "ha-1"}

    with TestClient(app) as client:
        empty = client.post("/v1/users/sync", json={**base, "display_name": "   "})
        overlong = client.post(
            "/v1/users/sync", json={**base, "display_name": "n" * 256}
        )

    assert empty.status_code == 422
    assert overlong.status_code == 422
