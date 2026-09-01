import pytest

from homeassistant.custom_components.nyra.esphome import EspHomeSpeakerOutput, SpeakerTarget
from shared.protocol.events import IdentityFeedback


@pytest.mark.asyncio
async def test_identity_feedback_uses_atomic_speaker_button():
    calls = []
    async def call(domain, service, data):
        calls.append((domain, service, data))
    output = EspHomeSpeakerOutput(
        {
            "speaker-a": SpeakerTarget(
                light_entity="light.speaker_a_led",
                identity_not_recognized_button="button.speaker_a_identity_not_recognized",
            )
        },
        call,
    )
    await output.blink_identity("speaker-a", IdentityFeedback.NOT_RECOGNIZED, 2)
    assert calls == [
        ("button", "press", {"entity_id": "button.speaker_a_identity_not_recognized"})
    ]
