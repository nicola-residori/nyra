from fastapi.testclient import TestClient

from router.app import create_app
from router.config import RouterSettings


class SpeakerAdmin:
    def __init__(self):
        self.calls = []

    async def json(self, method, path, *, params=None, payload=None):
        self.calls.append((method, path, params, payload))
        if path == "/v1/admin/profiles":
            return [{"user_id": "ha-1", "sample_count": 1, "samples": []}]
        if path == "/v1/admin/diagnostics":
            return [{
                "diagnostic_id": "diag-1",
                "outcome": "IDENTIFIED",
                "identified_user_id": "ha-1",
            }]
        if path == "/v1/admin/diagnostics/diag-1":
            return {
                "diagnostic_id": "diag-1",
                "candidates": [
                    {"user_id": "ha-1", "score": .82, "rank": 1},
                    {"user_id": "unknown", "score": .21, "rank": 2},
                ],
            }
        if path == "/v1/admin/wake-words":
            return [{
                "sample_id": "ww-1",
                "wake_word_text": "Nyra",
                "user_id": "ha-1",
            }]
        return {"deleted": 1}

    async def binary(self, method, path, *, payload=None):
        self.calls.append((method + "_BYTES", path, None, payload))
        if method == "POST":
            return b"archive", "application/gzip", "attachment; filename=x.tar.gz"
        return b"wav", "audio/wav", None


def app(tmp_path, speaker_admin):
    return create_app(
        RouterSettings(database_path=tmp_path / "router.db"), audio_sink=object(),
        speaker_id_admin=speaker_admin,
    )


def test_admin_reads_identity_data_only_through_router(tmp_path):
    upstream = SpeakerAdmin()
    router_app = app(tmp_path, upstream)
    with TestClient(router_app) as client:
        router_app.state.user_directory.upsert("home_assistant", "ha-1", "Nicola")
        profile = client.get("/v1/admin/speaker-identity/profiles").json()[0]
        diagnostic = client.get(
            "/v1/admin/speaker-identity/diagnostics",
            params={"source_id": "nyra-mansarda"},
        ).json()[0]
        detail = client.get(
            "/v1/admin/speaker-identity/diagnostics/diag-1"
        ).json()
        wake_word = client.get(
            "/v1/admin/speaker-identity/wake-words",
            params={"wake_word_text": "Nyra"},
        ).json()[0]
        audio = client.get("/v1/admin/speaker-identity/diagnostics/diag-1/audio")
        assert audio.content == b"wav"
        assert audio.headers["content-type"] == "audio/wav"

    assert profile["user_id"] == "ha-1"
    assert profile["user_display_name"] == "Nicola"
    assert diagnostic["identified_user_display_name"] == "Nicola"
    assert detail["candidates"][0]["user_display_name"] == "Nicola"
    assert detail["candidates"][1]["user_display_name"] is None
    assert wake_word["user_display_name"] == "Nicola"

    assert all("192.168" not in str(call) for call in upstream.calls)


def test_unknown_admin_user_ids_receive_an_explicit_null_name(tmp_path):
    upstream = SpeakerAdmin()
    router_app = app(tmp_path, upstream)
    with TestClient(router_app) as client:
        profile = client.get("/v1/admin/speaker-identity/profiles").json()[0]

    assert profile["user_id"] == "ha-1"
    assert profile["user_display_name"] is None


def test_admin_mutations_resolve_to_explicit_sample_ids(tmp_path):
    upstream = SpeakerAdmin()
    with TestClient(app(tmp_path, upstream)) as client:
        response = client.request(
            "DELETE", "/v1/admin/speaker-identity/profiles/user-nicola/samples",
            json={"sample_ids": ["one", "two"]},
        )
        assert response.json() == {"deleted": 1}
        export = client.post(
            "/v1/admin/speaker-identity/wake-words/export",
            json={"sample_ids": ["ww-1"]},
        )
        assert export.status_code == 200

    assert ("DELETE", "/v1/admin/profiles/user-nicola/samples", None, {"sample_ids": ["one", "two"]}) in upstream.calls
