from copy import deepcopy

from fastapi.testclient import TestClient

from router.app import create_app
from router.config import RouterSettings


class ExistingSpeakerIdProfile:
    def __init__(self):
        self.profile = {
            "user_id": "ha-existing-user",
            "sample_count": 1,
            "samples": [{
                "sample_id": "sample-1",
                "source_id": "nyra-mansarda",
            }],
        }

    async def json(self, method, path, *, params=None, payload=None):
        assert method == "GET"
        assert path == "/v1/admin/profiles"
        return [deepcopy(self.profile)]

    async def binary(self, method, path, *, payload=None):
        raise AssertionError("binary endpoint not expected")


def test_existing_id_only_profile_is_enriched_after_trusted_sync(tmp_path):
    speaker_id = ExistingSpeakerIdProfile()
    app = create_app(
        RouterSettings(database_path=tmp_path / "router.db"),
        audio_sink=object(),
        speaker_id_admin=speaker_id,
    )

    with TestClient(app) as client:
        before = client.get(
            "/v1/admin/speaker-identity/profiles"
        ).json()[0]
        synced = client.post("/v1/users/sync", json={
            "provider": "home_assistant",
            "user_id": "ha-existing-user",
            "display_name": "Nicola",
        })
        after = client.get(
            "/v1/admin/speaker-identity/profiles"
        ).json()[0]

    assert before["user_display_name"] is None
    assert synced.status_code == 200
    assert after["user_display_name"] == "Nicola"
    assert speaker_id.profile == {
        "user_id": "ha-existing-user",
        "sample_count": 1,
        "samples": [{
            "sample_id": "sample-1",
            "source_id": "nyra-mansarda",
        }],
    }
