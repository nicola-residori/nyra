from dataclasses import dataclass

import pytest

from homeassistant.custom_components.nyra.wake_word_capture import WakeWordCaptureCoordinator


class Client:
    def __init__(self):
        self.started = []
        self.completed = []

    async def async_start_wake_word_capture(self, **payload):
        self.started.append(payload)
        return {
            "session_id": "wwc_1", "user_id": payload["user_id"],
            "source_id": payload["source_id"], "language": payload["language"],
            "wake_word_text": payload["wake_word_text"], "status": "ACTIVE",
            "sample_id": None, "reason_code": None,
        }

    async def async_complete_wake_word_capture(self, session_id, result):
        self.completed.append((session_id, result))
        return {
            "session_id": session_id, "user_id": "user-nicola",
            "source_id": "nyra-mansarda", "language": "it-IT",
            "wake_word_text": "Nyra", "status": result["status"],
            "sample_id": result.get("sample_id"), "reason_code": result.get("reason_code"),
        }


class Output:
    def __init__(self):
        self.recorded = []

    async def record_wake_word_sample(self, source_id):
        self.recorded.append(source_id)


@dataclass(frozen=True)
class DeviceStart:
    audio_stream_id: str = "audio-1"
    session_id: str = "ses_1"
    request_id: str = "req_1"
    source_id: str = "nyra-mansarda"
    language: str = "it-IT"
    capture_purpose: str = "WAKE_WORD_CAPTURE"
    audio_format: str = "pcm_s16le"
    sample_rate: int = 16000
    channels: int = 1


@pytest.mark.asyncio
async def test_single_action_starts_session_and_device_recording():
    client = Client()
    output = Output()
    coordinator = WakeWordCaptureCoordinator(client, record_output=output)

    result = await coordinator.async_capture(
        authenticated_user_id="user-nicola", source_id="nyra-mansarda",
        language="it-IT", wake_word_text="  Nyra  ",
    )

    assert result["capture_state"] == "RECORDING"
    assert client.started[0]["wake_word_text"] == "Nyra"
    assert output.recorded == ["nyra-mansarda"]


@pytest.mark.asyncio
async def test_device_audio_is_correlated_and_result_terminates_session():
    client = Client()
    coordinator = WakeWordCaptureCoordinator(client, record_output=Output())
    await coordinator.async_capture(
        authenticated_user_id="user-nicola", source_id="nyra-mansarda",
        language="it-IT", wake_word_text="Nyra",
    )

    metadata = coordinator.audio_metadata(DeviceStart())
    assert metadata.purpose == "WAKE_WORD_CAPTURE"
    assert metadata.wake_word_session_id == "wwc_1"
    assert metadata.user_id == "user-nicola"
    assert metadata.wake_word_text == "Nyra"

    result = await coordinator.async_record_result(metadata, {
        "capture_id": "wwc_1", "status": "ACCEPTED",
        "sample_id": "sample-1", "reason_code": None,
    })

    assert result["status"] == "ACCEPTED"
    assert result["capture_state"] == "ACCEPTED"
    assert client.completed[0][0] == "wwc_1"
