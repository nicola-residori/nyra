import pytest
from homeassistant.custom_components.nyra.esphome import EspHomeSpeakerOutput, SpeakerTarget
from shared.protocol.events import IdentityFeedback


@pytest.mark.asyncio
async def test_esphome_output_uses_standard_ha_services_and_target_mapping():
    calls=[]
    async def call(domain,service,data): calls.append((domain,service,data))
    output=EspHomeSpeakerOutput({"speaker-a":SpeakerTarget("light.speaker_a_led","button.speaker_a_close")},call)
    await output.comet_turquoise("speaker-a")
    await output.blink_identity("speaker-a",IdentityFeedback.IDENTITY_CHANGED,2)
    await output.close_feedback("speaker-a")
    assert calls == [
        ("light","turn_on",{"entity_id":"light.speaker_a_led","effect":"nyra_processing_local_turquoise_comet"}),
        ("light","turn_on",{"entity_id":"light.speaker_a_led","effect":"nyra_identity_blue_2blink"}),
        ("button","press",{"entity_id":"button.speaker_a_close"}),
    ]
