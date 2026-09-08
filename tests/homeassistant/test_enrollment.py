import asyncio
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock

from homeassistant.custom_components.nyra.enrollment import (
    EnrollmentConflict,
    EnrollmentCoordinator,
    EnrollmentUnauthorized,
    handle_start_enrollment,
    handle_record_enrollment,
    handle_terminate_enrollment,
    localized_enrollment_message,
)
from homeassistant.custom_components.nyra.audio import IdentificationAudioStart


class Client:
    def __init__(self):
        self.started = []
        self.attempts = []
        self.terminations = []
        self.active = {}

    async def async_start_enrollment(self, **payload):
        self.started.append(payload)
        response = {
            "session_id": "enr_1", "profile_user_id": payload["profile_user_id"],
            "source_id": payload["source_id"], "language": payload["language"],
            "target_count": payload["target_count"], "accepted_count": 0,
            "accepted_sample_ids": [], "status": "ACTIVE", "termination_reason": None,
            "last_reason_code": None,
            "current_phrase": {"text": "Una frase.", "language": payload["language"], "length_class": "SHORT"},
        }
        self.active[payload["source_id"]] = response
        return response

    async def async_get_active_enrollment(self, source_id):
        return self.active.get(source_id)

    async def async_record_enrollment_attempt(self, session_id, result):
        self.attempts.append((session_id, result))
        return {**self.started_response, "accepted_count": 1, "status": "COMPLETED", "current_phrase": None}

    async def async_terminate_enrollment(self, session_id, reason):
        self.terminations.append((session_id, reason))
        return {**self.started_response, "status": "TERMINATED", "termination_reason": reason, "current_phrase": None}

    @property
    def started_response(self):
        payload = self.started[0]
        return {
            "session_id": "enr_1", "profile_user_id": payload["profile_user_id"],
            "source_id": payload["source_id"], "language": payload["language"],
            "target_count": payload["target_count"], "accepted_count": 0,
            "accepted_sample_ids": [], "status": "ACTIVE", "termination_reason": None,
            "last_reason_code": None,
            "current_phrase": {"text": "Una frase.", "language": payload["language"], "length_class": "SHORT"},
        }


def base_start(*, capture_purpose="IDENTIFICATION"):
    return IdentificationAudioStart(
        audio_stream_id="audio-1", session_id="ses_00000000-0000-4000-8000-000000000001",
        request_id="req_00000000-0000-4000-8000-000000000002", source_id="nyra-mansarda",
        language="it-IT",
        capture_purpose=capture_purpose,
    )


class RecordOutput:
    def __init__(self, *, error=None):
        self.recorded = []
        self.error = error

    async def record_enrollment_sample(self, source_id):
        if self.error is not None:
            raise self.error
        self.recorded.append(source_id)


@pytest.mark.asyncio
async def test_authenticated_ha_user_is_the_immutable_profile_binding():
    client = Client()
    coordinator = EnrollmentCoordinator(client, record_output=RecordOutput())

    session = await coordinator.async_start(
        authenticated_user_id="ha-real-user", source_id="nyra-mansarda",
        language="it-IT", target_count=1,
    )
    await coordinator.async_record("ha-real-user", session["session_id"])
    metadata = coordinator.audio_metadata(base_start(capture_purpose="ENROLLMENT_CAPTURE"))

    assert client.started == [{
        "profile_user_id": "ha-real-user", "source_id": "nyra-mansarda",
        "language": "it-IT", "target_count": 1,
    }]
    assert session["profile_user_id"] == "ha-real-user"
    assert metadata.purpose == "ENROLLMENT"
    assert metadata.user_id == "ha-real-user"
    assert metadata.enrollment_session_id == "enr_1"


@pytest.mark.asyncio
async def test_record_starts_one_capture_and_rejects_duplicates_and_other_users():
    output = RecordOutput()
    coordinator = EnrollmentCoordinator(Client(), record_output=output)
    session = await coordinator.async_start("ha-user", "nyra-mansarda", "it-IT", 6)

    recording = await coordinator.async_record("ha-user", session["session_id"])

    assert recording["capture_state"] == "RECORDING"
    assert output.recorded == ["nyra-mansarda"]
    with pytest.raises(EnrollmentConflict, match="already recording"):
        await coordinator.async_record("ha-user", session["session_id"])
    with pytest.raises(EnrollmentUnauthorized):
        await coordinator.async_record("another-user", session["session_id"])


@pytest.mark.asyncio
async def test_record_failure_restores_ready_state_and_notifies():
    updates = []
    coordinator = EnrollmentCoordinator(
        Client(), record_output=RecordOutput(error=RuntimeError("offline")),
        on_update=updates.append,
    )
    session = await coordinator.async_start("ha-user", "nyra-mansarda", "it-IT", 6)

    with pytest.raises(RuntimeError, match="offline"):
        await coordinator.async_record("ha-user", session["session_id"])

    assert coordinator.state_for_user("ha-user")[0]["capture_state"] == "READY"
    assert updates[-1]["capture_state"] == "READY"
    assert updates[-1]["capture_error"] == "SPEAKER_UNAVAILABLE"


@pytest.mark.asyncio
async def test_record_timeout_restores_panel_instead_of_staying_frozen():
    updates = []
    coordinator = EnrollmentCoordinator(
        Client(), record_output=RecordOutput(), on_update=updates.append,
        capture_timeout_seconds=0.01,
    )
    session = await coordinator.async_start("ha-user", "nyra-mansarda", "it-IT", 6)

    await coordinator.async_record("ha-user", session["session_id"])
    await asyncio.sleep(0.03)

    assert coordinator.state_for_user("ha-user")[0]["capture_state"] == "READY"
    assert updates[-1]["capture_error"] == "CAPTURE_TIMEOUT"


@pytest.mark.asyncio
async def test_restore_rebinds_router_active_session_after_reload():
    client = Client()
    existing = await client.async_start_enrollment(
        profile_user_id="ha-user", source_id="nyra-mansarda",
        language="it-IT", target_count=6,
    )
    coordinator = EnrollmentCoordinator(client, record_output=RecordOutput())

    restored = await coordinator.async_restore(["nyra-mansarda", "nyra-soggiorno"])

    assert restored == [existing]
    assert coordinator.state_for_user("ha-user")[0]["session_id"] == "enr_1"
    assert coordinator.state_for_user("ha-user")[0]["capture_state"] == "READY"


@pytest.mark.asyncio
async def test_restore_does_not_reset_an_in_flight_capture():
    client = Client()
    coordinator = EnrollmentCoordinator(client, record_output=RecordOutput())
    session = await coordinator.async_start("ha-user", "nyra-mansarda", "it-IT", 6)
    await coordinator.async_record("ha-user", session["session_id"])

    await coordinator.async_restore(["nyra-mansarda"])

    assert coordinator.state_for_user("ha-user")[0]["capture_state"] == "RECORDING"


@pytest.mark.asyncio
async def test_idempotent_start_rebinds_router_session_in_fresh_coordinator():
    client = Client()
    existing = await client.async_start_enrollment(
        profile_user_id="ha-user", source_id="nyra-mansarda",
        language="it-IT", target_count=6,
    )

    session = await EnrollmentCoordinator(client).async_start(
        "ha-user", "nyra-mansarda", "it-IT", 6
    )

    assert session["session_id"] == existing["session_id"]


@pytest.mark.asyncio
async def test_normal_identification_is_never_rewritten_during_enrollment():
    coordinator = EnrollmentCoordinator(Client())
    await coordinator.async_start("ha-user", "nyra-mansarda", "it-IT", 1)

    metadata = coordinator.audio_metadata(base_start())

    assert metadata.purpose == "IDENTIFICATION"
    assert not hasattr(metadata, "user_id")


def test_explicit_enrollment_capture_without_session_is_rejected():
    coordinator = EnrollmentCoordinator(Client())

    with pytest.raises(EnrollmentConflict, match="no active enrollment"):
        coordinator.audio_metadata(base_start(capture_purpose="ENROLLMENT_CAPTURE"))


@pytest.mark.asyncio
async def test_explicit_capture_requires_a_pending_record_request():
    coordinator = EnrollmentCoordinator(Client(), record_output=RecordOutput())
    await coordinator.async_start("ha-user", "nyra-mansarda", "it-IT", 1)

    with pytest.raises(EnrollmentConflict, match="no pending enrollment recording"):
        coordinator.audio_metadata(base_start(capture_purpose="ENROLLMENT_CAPTURE"))


@pytest.mark.asyncio
async def test_anonymous_ha_service_cannot_start_enrollment():
    with pytest.raises(EnrollmentUnauthorized):
        await EnrollmentCoordinator(Client()).async_start(
            authenticated_user_id=None, source_id="nyra-mansarda", language="it-IT", target_count=6
        )


@pytest.mark.asyncio
async def test_audio_result_advances_router_session_and_disables_terminal_capture():
    client = Client()
    updates = []
    coordinator = EnrollmentCoordinator(client, record_output=RecordOutput(), on_update=updates.append)
    await coordinator.async_start("ha-user", "nyra-mansarda", "it-IT", 1)
    await coordinator.async_record("ha-user", "enr_1")
    metadata = coordinator.audio_metadata(base_start(capture_purpose="ENROLLMENT_CAPTURE"))

    completed = await coordinator.async_record_result(metadata, {
        "status": "ACCEPTED", "sample_id": "sample-1", "user_id": "ha-user",
    })

    assert completed["status"] == "COMPLETED"
    assert completed["capture_state"] == "COMPLETED"
    assert updates[-1]["capture_state"] == "COMPLETED"
    assert client.attempts == [("enr_1", {
        "status": "ACCEPTED", "sample_id": "sample-1", "reason_code": None,
    })]
    assert coordinator.audio_metadata(base_start()).purpose == "IDENTIFICATION"
    with pytest.raises(EnrollmentConflict, match="no active enrollment"):
        coordinator.audio_metadata(base_start(capture_purpose="ENROLLMENT_CAPTURE"))


@pytest.mark.parametrize(
    "language,status,reason,expected",
    [
        ("it-IT", "COMPLETED", None, "Ho completato la registrazione della tua voce."),
        ("en-US", "COMPLETED", None, "I have completed your voice enrollment."),
        ("it-IT", "ACTIVE", "TOO_SHORT", "Il campione è troppo breve. Ripeti la stessa frase."),
        ("en-US", "ACTIVE", "TOO_SHORT", "The sample is too short. Repeat the same phrase."),
    ],
)
def test_localized_completion_and_reason_messages(language, status, reason, expected):
    assert localized_enrollment_message(language, status, reason) == expected


@pytest.mark.asyncio
async def test_service_handler_uses_context_user_and_ignores_supplied_profile_id():
    client = Client()
    coordinator = EnrollmentCoordinator(client)
    call = SimpleNamespace(
        context=SimpleNamespace(user_id="authenticated-user"),
        data={"source_id": "nyra-mansarda", "language": "en-US", "sample_count": 1,
              "profile_user_id": "forged-user"},
    )

    result = await handle_start_enrollment(call, coordinator)

    assert result["profile_user_id"] == "authenticated-user"
    assert client.started[0]["profile_user_id"] == "authenticated-user"


@pytest.mark.asyncio
async def test_service_handler_syncs_name_from_home_assistant_auth_only():
    class SyncingClient(Client):
        def __init__(self):
            super().__init__()
            self.synced = []

        async def async_sync_user_reference(self, **payload):
            self.synced.append(payload)
            return True

    client = SyncingClient()
    coordinator = EnrollmentCoordinator(client)
    hass = SimpleNamespace(auth=SimpleNamespace(
        async_get_user=AsyncMock(return_value=SimpleNamespace(
            id="authenticated-user", name="Nicola"
        ))
    ))
    call = SimpleNamespace(
        context=SimpleNamespace(user_id="authenticated-user"),
        data={
            "source_id": "nyra-mansarda",
            "display_name": "Nome falsificato",
        },
    )

    await handle_start_enrollment(call, coordinator, hass)

    assert client.synced == [{
        "user_id": "authenticated-user",
        "display_name": "Nicola",
        "provider": "home_assistant",
    }]


@pytest.mark.asyncio
async def test_record_service_handler_uses_context_user():
    output = RecordOutput()
    coordinator = EnrollmentCoordinator(Client(), record_output=output)
    await coordinator.async_start("authenticated-user", "nyra-mansarda", "it-IT", 6)
    call = SimpleNamespace(
        context=SimpleNamespace(user_id="authenticated-user"),
        data={"session_id": "enr_1", "profile_user_id": "forged-user"},
    )

    result = await handle_record_enrollment(call, coordinator)

    assert result["capture_state"] == "RECORDING"
    assert output.recorded == ["nyra-mansarda"]


@pytest.mark.asyncio
async def test_terminate_service_checks_same_authenticated_user():
    client = Client()
    coordinator = EnrollmentCoordinator(client)
    await coordinator.async_start("owner", "nyra-mansarda", "it-IT", 1)
    forged = SimpleNamespace(
        context=SimpleNamespace(user_id="someone-else"),
        data={"session_id": "enr_1"},
    )
    with pytest.raises(EnrollmentUnauthorized):
        await handle_terminate_enrollment(forged, coordinator)
