from fastapi.testclient import TestClient

from router.app import create_app
from router.config import RouterSettings


def test_enrollment_api_binds_profile_and_advances_only_on_accept(tmp_path):
    app = create_app(RouterSettings(database_path=tmp_path / "router.db", ingress_token="secret"))
    headers = {"Authorization": "Bearer secret"}
    payload = {
        "profile_user_id": "ha-user-1",
        "source_id": "nyra-mansarda",
        "language": "it-IT",
        "target_count": 2,
    }

    with TestClient(app) as client:
        assert client.post("/v1/enrollments", json=payload).status_code == 401
        created = client.post(
            "/v1/enrollments",
            headers=headers,
            json=payload,
        )
        assert created.status_code == 201
        session = created.json()
        session_id = session["session_id"]
        phrase = session["current_phrase"]

        rejected = client.post(
            f"/v1/enrollments/{session_id}/attempts",
            headers=headers,
            json={"status": "REJECTED", "reason_code": "TOO_SHORT"},
        ).json()
        assert rejected["accepted_count"] == 0
        assert rejected["current_phrase"] == phrase

        first = client.post(
            f"/v1/enrollments/{session_id}/attempts",
            headers=headers,
            json={"status": "ACCEPTED", "sample_id": "sample-a"},
        ).json()
        assert first["accepted_count"] == 1
        assert first["current_phrase"] != phrase

        completed = client.post(
            f"/v1/enrollments/{session_id}/attempts",
            headers=headers,
            json={"status": "ACCEPTED", "sample_id": "sample-b"},
        ).json()
        assert completed["status"] == "COMPLETED"
        assert completed["accepted_sample_ids"] == ["sample-a", "sample-b"]


def test_enrollment_api_rejects_invalid_accept_and_conflicting_terminal_update(tmp_path):
    app = create_app(RouterSettings(database_path=tmp_path / "router.db"))
    with TestClient(app) as client:
        created = client.post("/v1/enrollments", json={
            "profile_user_id": "u", "source_id": "s", "language": "en-US", "target_count": 2,
        }).json()
        session_id = created["session_id"]
        assert client.post(
            f"/v1/enrollments/{session_id}/attempts", json={"status": "ACCEPTED"}
        ).status_code == 422
        assert client.post(
            f"/v1/enrollments/{session_id}/terminate", json={"reason": "cancelled"}
        ).status_code == 200
        assert client.post(
            f"/v1/enrollments/{session_id}/terminate", json={"reason": "other"}
        ).status_code == 409


def test_enrollment_start_is_idempotent_and_active_source_is_recoverable(tmp_path):
    app = create_app(RouterSettings(database_path=tmp_path / "router.db", ingress_token="secret"))
    headers = {"Authorization": "Bearer secret"}
    payload = {
        "profile_user_id": "ha-user-1",
        "source_id": "nyra-mansarda",
        "language": "it-IT",
        "target_count": 6,
    }

    with TestClient(app) as client:
        first = client.post("/v1/enrollments", headers=headers, json=payload)
        second = client.post("/v1/enrollments", headers=headers, json=payload)
        assert second.status_code == 201
        assert second.json()["session_id"] == first.json()["session_id"]

        active = client.get("/v1/enrollments/active/nyra-mansarda", headers=headers)
        assert active.status_code == 200
        assert active.json()["session_id"] == first.json()["session_id"]

        conflict = client.post(
            "/v1/enrollments",
            headers=headers,
            json={**payload, "profile_user_id": "ha-user-2"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"] == "ACTIVE_ENROLLMENT_CONFLICT"

        client.post(
            f"/v1/enrollments/{first.json()['session_id']}/terminate",
            headers=headers,
            json={"reason": "cancelled"},
        )
        assert client.get(
            "/v1/enrollments/active/nyra-mansarda", headers=headers
        ).status_code == 404
