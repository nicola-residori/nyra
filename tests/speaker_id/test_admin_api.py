from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from tests.speaker_id.test_health import ReadyEngine, load_module


@dataclass(frozen=True)
class Processed:
    wav_bytes: bytes
    preprocessing_version: str = "prep-1"
    duration_seconds: float = 1.1
    quality: dict = None


@dataclass(frozen=True)
class Snapshot:
    threshold: float = .4
    margin: float = .07
    revision: int = 1


def test_admin_apis_expose_profiles_diagnostics_and_wake_word_audio(tmp_path):
    module = load_module()
    app = module.create_app(data_root=tmp_path, embedding_engine=ReadyEngine())

    with TestClient(app) as client:
        profile_sample = app.state.profile_store.add_sample(
            user_id="user-nicola", source_id="nyra-mansarda", wav_bytes=b"profile-wav",
            embedding=[1.0], quality={"rms": .2}, duration_seconds=1.2,
            created_at=datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc),
        )
        diagnostic_wav = tmp_path / "diagnostic.wav"
        diagnostic_wav.write_bytes(b"diagnostic-wav")
        diagnostic_id = app.state.diagnostic_store.record(
            outcome="IDENTIFIED", identified_user_id="user-nicola", best_score=.82,
            reason_code=None, candidate_scores={"user-nicola": .82, "other": .31},
            preprocessing_version="prep-1", model_revision="ecapa",
            config_snapshot=Snapshot(), diagnostic_wav_path=diagnostic_wav,
            source_id="nyra-mansarda", request_id="req_1", trace_id="trc_1",
        )
        ww = app.state.wake_word_store.complete_capture(
            capture_id="wwc_1", status="ACCEPTED", wake_word_text="Nyra",
            user_id="user-nicola", source_id="nyra-mansarda", language="it-IT",
            created_at=datetime(2026, 9, 7, 18, 1, tzinfo=timezone.utc),
            processed_audio=Processed(b"wake-wav", quality={"rms": .3}),
        )

        profiles = client.get("/v1/admin/profiles").json()
        assert profiles[0]["user_id"] == "user-nicola"
        assert profiles[0]["samples"][0]["duration_seconds"] == 1.2
        assert "embedding" not in profiles[0]["samples"][0]
        assert client.get(f"/v1/admin/profiles/user-nicola/samples/{profile_sample.sample_id}/audio").content == b"profile-wav"

        diagnostics = client.get("/v1/admin/diagnostics", params={"source_id": "nyra-mansarda"}).json()
        assert diagnostics[0]["diagnostic_id"] == diagnostic_id
        detail = client.get(f"/v1/admin/diagnostics/{diagnostic_id}").json()
        assert [item["user_id"] for item in detail["candidates"]] == ["user-nicola", "other"]
        assert client.get(f"/v1/admin/diagnostics/{diagnostic_id}/audio").content == b"diagnostic-wav"

        wake_words = client.get("/v1/admin/wake-words", params={"wake_word_text": "nyra"}).json()
        assert wake_words[0]["sample_id"] == ww.sample_id
        assert wake_words[0]["quality"] == {"rms": .3}
        assert client.get(f"/v1/admin/wake-words/samples/{ww.sample_id}/audio").content == b"wake-wav"
        exported = client.post("/v1/admin/wake-words/export", json={"sample_ids": [ww.sample_id]})
        assert exported.status_code == 200
        assert exported.headers["content-type"] == "application/gzip"


def test_admin_can_delete_selected_enrollment_and_wake_word_samples(tmp_path):
    module = load_module()
    app = module.create_app(data_root=tmp_path, embedding_engine=ReadyEngine())
    with TestClient(app) as client:
        profile = app.state.profile_store.add_sample(
            user_id="u", source_id="s", wav_bytes=b"p", embedding=[1.0], quality={}
        )
        wake = app.state.wake_word_store.complete_capture(
            capture_id="c", status="ACCEPTED", wake_word_text="Nyra", user_id="u",
            source_id="s", language="it", created_at=datetime.now(timezone.utc),
            processed_audio=Processed(b"w", quality={}),
        )

        assert client.request("DELETE", "/v1/admin/profiles/u/samples", json={"sample_ids": [profile.sample_id]}).json() == {"deleted": 1}
        assert client.request("DELETE", "/v1/admin/wake-words/samples", json={"sample_ids": [wake.sample_id]}).json() == {"deleted": 1}


def test_admin_does_not_serve_expired_diagnostic_details_or_audio(tmp_path):
    module = load_module()
    app = module.create_app(data_root=tmp_path, embedding_engine=ReadyEngine())
    with TestClient(app) as client:
        diagnostic_wav = tmp_path / "expired-diagnostic.wav"
        diagnostic_wav.write_bytes(b"expired")
        diagnostic_id = app.state.diagnostic_store.record(
            outcome="IDENTIFIED", identified_user_id="user-nicola", best_score=.82,
            reason_code=None, candidate_scores={"user-nicola": .82},
            preprocessing_version="prep-1", model_revision="ecapa",
            config_snapshot=Snapshot(), diagnostic_wav_path=diagnostic_wav,
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        item = client.get("/v1/admin/diagnostics").json()[0]
        detail = client.get(f"/v1/admin/diagnostics/{diagnostic_id}").json()

        assert item["audio_available"] is False
        assert detail["details_available"] is False
        assert detail["candidates"] == []
        assert client.get(f"/v1/admin/diagnostics/{diagnostic_id}/audio").status_code == 404
