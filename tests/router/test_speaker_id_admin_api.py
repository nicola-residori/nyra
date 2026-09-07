from fastapi.testclient import TestClient

from router.app import create_app
from router.config import RouterSettings


class SpeakerAdmin:
    def __init__(self):
        self.calls = []

    async def json(self, method, path, *, params=None, payload=None):
        self.calls.append((method, path, params, payload))
        if path == "/v1/admin/profiles":
            return [{"user_id": "user-nicola", "sample_count": 1, "samples": []}]
        if path == "/v1/admin/diagnostics":
            return [{"diagnostic_id": "diag-1", "outcome": "IDENTIFIED"}]
        if path == "/v1/admin/wake-words":
            return [{"sample_id": "ww-1", "wake_word_text": "Nyra"}]
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
    with TestClient(app(tmp_path, upstream)) as client:
        assert client.get("/v1/admin/speaker-identity/profiles").json()[0]["user_id"] == "user-nicola"
        assert client.get("/v1/admin/speaker-identity/diagnostics", params={"source_id": "nyra-mansarda"}).json()[0]["diagnostic_id"] == "diag-1"
        assert client.get("/v1/admin/speaker-identity/wake-words", params={"wake_word_text": "Nyra"}).json()[0]["sample_id"] == "ww-1"
        audio = client.get("/v1/admin/speaker-identity/diagnostics/diag-1/audio")
        assert audio.content == b"wav"
        assert audio.headers["content-type"] == "audio/wav"

    assert all("192.168" not in str(call) for call in upstream.calls)


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
