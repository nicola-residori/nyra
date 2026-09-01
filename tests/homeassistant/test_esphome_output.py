import pytest

from homeassistant.custom_components.nyra.esphome import (
    EspHomeSpeakerOutput,
    SpeakerTarget,
    discover_speaker_targets,
)
from shared.protocol.events import IdentityFeedback


@pytest.mark.asyncio
async def test_esphome_output_uses_standard_ha_services_and_target_mapping():
    calls = []

    async def call(domain, service, data):
        calls.append((domain, service, data))

    output = EspHomeSpeakerOutput(
        {
            "speaker-a": SpeakerTarget(
                    light_entity="light.speaker_a_led",
                    close_feedback_button="button.speaker_a_close",
                    identity_changed_button="button.speaker_a_identity_changed",
                )
        },
        call,
    )

    await output.comet_turquoise("speaker-a")
    await output.blink_identity(
        "speaker-a",
        IdentityFeedback.IDENTITY_CHANGED,
        2,
    )
    await output.close_feedback("speaker-a")

    assert calls == [
        (
            "light",
            "turn_on",
            {
                "entity_id": "light.speaker_a_led",
                "effect": "nyra_processing_local_turquoise_comet",
            },
        ),
        (
            "button",
            "press",
            {"entity_id": "button.speaker_a_identity_changed"},
        ),
        ("button", "press", {"entity_id": "button.speaker_a_close"}),
    ]


@pytest.mark.asyncio
async def test_esphome_output_never_falls_back_to_another_speaker():
    calls = []
    resolutions = 0

    async def call(domain, service, data):
        calls.append((domain, service, data))

    async def resolve_targets():
        nonlocal resolutions
        resolutions += 1
        return {
            "speaker-b": SpeakerTarget(
                "light.speaker_b_led",
                "button.speaker_b_close",
            )
        }

    output = EspHomeSpeakerOutput(
        {
            "speaker-a": SpeakerTarget(
                "light.speaker_a_led",
                "button.speaker_a_close",
            )
        },
        call,
        resolve_targets=resolve_targets,
    )

    await output.blink_identity(
        "missing-speaker",
        IdentityFeedback.NOT_RECOGNIZED,
        2,
    )

    assert resolutions == 1
    assert calls == []


def test_discovery_joins_source_id_ring_and_close_feedback_by_device():
    devices = [{"id": "device-a", "name": "Bedroom Voice Assistant"}]
    entities = [
        {
            "device_id": "device-a",
            "entity_id": "sensor.renamed_source_identity",
            "platform": "esphome",
            "original_name": "Nyra Source ID",
        },
        {
            "device_id": "device-a",
            "entity_id": "light.user_renamed_ring",
            "platform": "esphome",
            "original_name": "Nyra Status Ring",
        },
        {
            "device_id": "device-a",
            "entity_id": "button.user_renamed_close",
            "platform": "esphome",
            "original_name": "Nyra Close Feedback",
        },
    ]
    states = {"sensor.renamed_source_identity": "nyra-bedroom"}

    assert discover_speaker_targets(devices, entities, states) == {
        "nyra-bedroom": SpeakerTarget(
            light_entity="light.user_renamed_ring",
            close_feedback_button="button.user_renamed_close",
        )
    }


def test_discovery_accepts_status_ring_without_close_feedback():
    devices = [{"id": "device-a", "name": "Voice Assistant"}]
    entities = [
        {
            "device_id": "device-a",
            "entity_id": "sensor.source",
            "platform": "esphome",
            "original_name": "Nyra Source ID",
        },
        {
            "device_id": "device-a",
            "entity_id": "light.ring",
            "platform": "esphome",
            "original_name": "Nyra Status Ring",
        },
    ]
    states = {"sensor.source": "nyra-bedroom"}

    assert discover_speaker_targets(devices, entities, states) == {
        "nyra-bedroom": SpeakerTarget(
            light_entity="light.ring",
            close_feedback_button=None,
        )
    }


def test_discovery_ignores_device_without_nyra_source_id():
    devices = [{"id": "device-a", "name": "Voice Assistant"}]
    entities = [
        {
            "device_id": "device-a",
            "entity_id": "light.ring",
            "platform": "esphome",
            "original_name": "Nyra Status Ring",
        },
        {
            "device_id": "device-a",
            "entity_id": "button.close",
            "platform": "esphome",
            "original_name": "Nyra Close Feedback",
        },
    ]

    assert discover_speaker_targets(devices, entities, {}) == {}


@pytest.mark.asyncio
async def test_esphome_output_resolves_speaker_that_appears_after_setup():
    calls = []
    available = False

    async def call(domain, service, data):
        calls.append((domain, service, data))

    async def resolve_targets():
        if not available:
            return {}
        return {
            "speaker-a": SpeakerTarget(
                "light.speaker_a_led",
                "button.speaker_a_close",
            )
        }

    output = EspHomeSpeakerOutput(
        {},
        call,
        resolve_targets=resolve_targets,
    )

    await output.comet_turquoise("speaker-a")
    assert calls == []

    available = True
    await output.comet_turquoise("speaker-a")

    assert calls == [
        (
            "light",
            "turn_on",
            {
                "entity_id": "light.speaker_a_led",
                "effect": "nyra_processing_local_turquoise_comet",
            },
        )
    ]


@pytest.mark.asyncio
async def test_esphome_output_re_resolves_missing_source_without_reload():
    calls = []
    resolutions = 0

    async def call(domain, service, data):
        calls.append((domain, service, data))

    async def resolve_targets():
        nonlocal resolutions
        resolutions += 1
        if resolutions == 1:
            return {}
        return {
            "speaker-b": SpeakerTarget(
                "light.speaker_b_led",
                None,
            )
        }

    output = EspHomeSpeakerOutput(
        {},
        call,
        resolve_targets=resolve_targets,
    )

    await output.pulse_white_fast("speaker-b")
    await output.pulse_white_fast("speaker-b")

    assert resolutions == 2
    assert calls == [
        (
            "light",
            "turn_on",
            {
                "entity_id": "light.speaker_b_led",
                "effect": "Pulse Fast",
            },
        )
    ]
