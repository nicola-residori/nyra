from pathlib import Path

import pytest

from router.app import create_app
from router.config import RouterSettings


def test_router_wake_word_capture_api_is_single_attempt(tmp_path: Path):
    from fastapi.testclient import TestClient

    app = create_app(RouterSettings(database_path=tmp_path / "router.db"), audio_sink=object())
    with TestClient(app) as client:
        started = client.post("/v1/wake-word-captures", json={
            "user_id": "user-nicola",
            "source_id": "nyra-mansarda",
            "language": "it-IT",
            "wake_word_text": "Nyra",
        })
        assert started.status_code == 201
        session_id = started.json()["session_id"]

        accepted = client.post(
            f"/v1/wake-word-captures/{session_id}/result",
            json={"status": "ACCEPTED", "sample_id": "sample-1"},
        )
        assert accepted.status_code == 200
        assert accepted.json()["status"] == "ACCEPTED"

        duplicate = client.post(
            f"/v1/wake-word-captures/{session_id}/result",
            json={"status": "ACCEPTED", "sample_id": "sample-2"},
        )
        assert duplicate.status_code == 409


@pytest.mark.parametrize(
    ("terminal", "body"),
    [
        ("REJECTED", {"status": "REJECTED", "reason_code": "TOO_SHORT"}),
        ("FAILED", {"status": "FAILED", "reason_code": "STORAGE_UNAVAILABLE"}),
    ],
)
def test_router_wake_word_capture_preserves_nonaccepted_terminal_result(
    tmp_path: Path, terminal: str, body: dict
):
    from fastapi.testclient import TestClient

    app = create_app(RouterSettings(database_path=tmp_path / "router.db"), audio_sink=object())
    with TestClient(app) as client:
        started = client.post("/v1/wake-word-captures", json={
            "user_id": "user-nicola",
            "source_id": "nyra-mansarda",
            "language": "en-US",
            "wake_word_text": "Computer",
        }).json()
        result = client.post(
            f"/v1/wake-word-captures/{started['session_id']}/result", json=body
        )

    assert result.status_code == 200
    assert result.json()["status"] == terminal
    assert result.json()["reason_code"] == body["reason_code"]
    assert result.json()["sample_id"] is None


def test_router_proxies_dataset_count_without_exposing_speaker_id(tmp_path: Path):
    from fastapi.testclient import TestClient

    class Dataset:
        async def count(self, wake_word_text):
            assert wake_word_text == "Nyra"
            return 4

    app = create_app(
        RouterSettings(database_path=tmp_path / "router.db"),
        audio_sink=object(), wake_word_dataset=Dataset(),
    )
    with TestClient(app) as client:
        response = client.get(
            "/v1/wake-word-captures/sample-count", params={"wake_word_text": "Nyra"}
        )

    assert response.status_code == 200
    assert response.json() == {"wake_word_text": "Nyra", "sample_count": 4}
