import httpx
from fastapi.testclient import TestClient

from admin.app import create_app
from admin.client import RouterClient
from admin.config import AdminSettings


def app(user_display_name="Nicola"):
    async def handler(request):
        path = request.url.path
        if path.endswith("/profiles"):
            return httpx.Response(200, json=[{
                "user_id": "user-nicola", "sample_count": 1,
                "user_display_name": user_display_name,
                "samples": [{"sample_id": "enr-1", "source_id": "nyra-mansarda",
                             "created_at": "2026-09-07T18:00:00Z", "duration_seconds": 1.2,
                             "quality": {"rms": .2}, "preprocessing_version": "1"}],
            }])
        if path.endswith("/diagnostics"):
            return httpx.Response(200, json=[{
                "diagnostic_id": "diag-1", "created_at": "2026-09-07T18:01:00Z",
                "source_id": "nyra-mansarda", "outcome": "IDENTIFIED",
                "identified_user_id": "user-nicola", "best_score": .82,
                "identified_user_display_name": user_display_name,
                "reason_code": None, "audio_available": True,
            }])
        if path.endswith("/diagnostics/diag-1"):
            return httpx.Response(200, json={
                "diagnostic_id": "diag-1", "candidates": [
                    {"user_id": "user-nicola", "user_display_name": user_display_name,
                     "score": .82, "rank": 1}
                ]
            })
        if path.endswith("/wake-words"):
            return httpx.Response(200, json=[{
                "sample_id": "ww-1", "wake_word_text": "Nyra", "user_id": "user-nicola",
                "user_display_name": user_display_name,
                "source_id": "nyra-mansarda", "created_at": "2026-09-07T18:02:00Z",
                "duration_seconds": 1.0, "quality": {"rms": .3}, "language": "it-IT",
            }])
        if "/audio" in path:
            return httpx.Response(200, content=b"wav", headers={"content-type": "audio/wav"})
        if path.endswith("/export"):
            return httpx.Response(200, content=b"archive", headers={"content-type": "application/gzip"})
        return httpx.Response(200, json={"deleted": 1})

    router = RouterClient("http://router", transport=httpx.MockTransport(handler))
    return create_app(AdminSettings(), router)


def test_identity_pages_show_required_data_and_audio_controls():
    with TestClient(app()) as client:
        profiles = client.get("/identity/profiles").text
        assert "Profili vocali" in profiles
        assert '<h3 class="user-name">Nicola</h3>' in profiles
        assert '<code class="user-id">user-nicola</code>' in profiles
        assert "user-nicola" in profiles
        assert "nyra-mansarda" in profiles
        assert "<audio" in profiles
        assert "1.2" in profiles

        diagnostics = client.get("/identity/diagnostics").text
        assert "Controlli identità" in diagnostics
        assert '<span class="user-name">Nicola</span>' in diagnostics
        assert '<code class="user-id">user-nicola</code>' in diagnostics
        assert "IDENTIFIED" in diagnostics
        assert "0.82" in diagnostics
        assert "Candidati" in diagnostics
        assert "<audio" in diagnostics

        wake_words = client.get("/wake-words").text
        assert "Campioni wake word" in wake_words
        assert '<span class="user-name">Nicola</span>' in wake_words
        assert '<code class="user-id">user-nicola</code>' in wake_words
        assert "Nyra" in wake_words
        assert "<audio" in wake_words
        assert "Esporta selezionati" in wake_words


def test_identity_pages_fall_back_to_the_stable_id_when_name_is_missing():
    with TestClient(app(None)) as client:
        profiles = client.get("/identity/profiles").text
        diagnostics = client.get("/identity/diagnostics").text
        wake_words = client.get("/wake-words").text

    assert '<h3 class="user-name">user-nicola</h3>' in profiles
    assert '<span class="user-name">user-nicola</span>' in diagnostics
    assert '<span class="user-name">user-nicola</span>' in wake_words


def test_admin_has_management_only_and_no_capture_start_controls():
    with TestClient(app()) as client:
        combined = " ".join([
            client.get("/identity/profiles").text,
            client.get("/identity/diagnostics").text,
            client.get("/wake-words").text,
        ]).lower()

    assert "start enrollment" not in combined
    assert "inizia registrazione" not in combined
    assert "start capture" not in combined


def test_admin_proxies_audio_delete_and_export_through_router():
    with TestClient(app()) as client:
        assert client.get("/admin-api/speaker-identity/diagnostics/diag-1/audio").content == b"wav"
        deleted = client.request(
            "DELETE", "/admin-api/speaker-identity/wake-words/samples",
            json={"sample_ids": ["ww-1"]},
        )
        assert deleted.json() == {"deleted": 1}
        exported = client.post(
            "/admin-api/speaker-identity/wake-words/export",
            json={"sample_ids": ["ww-1"]},
        )
        assert exported.content == b"archive"


def test_admin_authenticates_identity_requests_to_router():
    seen_authorization = []

    async def handler(request):
        seen_authorization.append(request.headers.get("authorization"))
        return httpx.Response(200, json=[])

    router = RouterClient(
        "http://router",
        transport=httpx.MockTransport(handler),
        token="router-secret",
    )
    secured_app = create_app(AdminSettings(), router)

    with TestClient(secured_app) as client:
        assert client.get("/identity/profiles").status_code == 200

    assert seen_authorization == ["Bearer router-secret"]
