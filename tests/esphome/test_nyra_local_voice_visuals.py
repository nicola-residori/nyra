from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _speaker_yaml() -> str:
    return (ROOT / "esphome/packages/nyra-speaker.yaml").read_text(encoding="utf-8")


def test_pre_router_voice_phases_keep_nyra_listening_visual():
    text = _speaker_yaml()
    assert "voice_assistant:" in text
    for hook in ("on_listening:", "on_stt_vad_start:", "on_stt_vad_end:", "on_stt_end:"):
        assert hook in text
    listening_start = text.index("on_listening:")
    listening_block = text[listening_start:listening_start + 1200]
    assert 'effect: "Pulse Fast"' in listening_block or "effect: Pulse Fast" in listening_block
    assert text.count('effect: "nyra_listening_white_fast"') >= 3


def test_listening_visual_is_a_continuous_fast_white_fade():
    text = _speaker_yaml()

    effect = text.split('name: "nyra_listening_white_fast"', 1)[1].split(
        '- addressable_lambda:', 1
    )[0]
    assert "update_interval: 30ms" in effect
    assert "const float phase" in effect
    assert "const float brightness" in effect
    assert "Color(level, level, level)" in effect
    assert "const bool on" not in effect


def test_voice_assistant_end_releases_nyra_ring_ownership():
    text = _speaker_yaml()
    voice = text.split("voice_assistant:", 1)[1].split("light:", 1)[0]

    # Purple speaking feedback is driven by actual announcement playback,
    # not by the Voice Assistant TTS-generation lifecycle.
    if "on_tts_start:" in voice:
        tts_start = voice.split("on_tts_start:", 1)[1].split("on_end:", 1)[0]
        assert 'effect: "nyra_speaking_purple_audio"' not in tts_start

    assert "on_end:" in voice
    end = voice.split("on_end:", 1)[1]
    assert "id(nyra_ring_owned) = false" in end
    assert "- light.turn_off: status_ring" in end


def test_nyra_ownership_gates_waveshare_phase_led_controller():
    text = _speaker_yaml()

    assert "id: nyra_ring_owned" in text
    assert "type: bool" in text
    assert "initial_value: 'false'" in text

    # ESPHome package list items are removed by tagging the id value:
    #   - id: !remove control_leds
    # not by tagging the whole list item.
    assert "id: !remove control_leds" in text
    assert "id: control_leds" in text
    assert "id: !remove led_set_effect" not in text
    assert "- !remove led_set_effect" not in text

    controller = text.split("id: !remove control_leds", 1)[1].split(
        "- id: nyra_close_feedback_sequence", 1
    )[0]
    assert "if (id(nyra_ring_owned))" in controller
    assert "return;" in controller
    assert "id(check_if_timers_active).execute();" in controller
    assert "id(led_set_effect).execute(effect, r, g, b);" in controller
    assert "switch (phase)" in controller
    assert 'set("off", 0, 0, 0);' in controller

    voice = text.split("voice_assistant:", 1)[1].split("light:", 1)[0]
    listening = voice.split("on_listening:", 1)[1].split("on_stt_vad_start:", 1)[0]
    assert "id(nyra_ring_owned) = true" in listening

    end = voice.split("on_end:", 1)[1]
    assert "id(nyra_ring_owned) = false" in end

def test_actual_announcement_temporarily_owns_ring_and_requests_semantic_restore():
    """Real announcement playback, not TTS generation, owns the purple override."""
    text = _speaker_yaml()

    assert "id: nyra_speaking_active" in text
    assert "type: bool" in text
    assert "initial_value: 'false'" in text

    voice = text.split("voice_assistant:", 1)[1].split("light:", 1)[0]
    if "on_tts_start:" in voice:
        tts_start = voice.split("on_tts_start:", 1)[1].split("on_end:", 1)[0]
        assert "nyra_speaking_purple_audio" not in tts_start

    assert "id: !extend external_media_player" in text
    media = text.split("id: !extend external_media_player", 1)[1]
    assert "on_state:" in media
    assert "media_player.is_announcing:" in media

    assert "id(nyra_ring_owned)" in media
    assert "id(nyra_speaking_active)" in media
    assert "nyra_speaking_purple_audio" in media

    assert "esphome.nyra_speaking_started" in media
    assert "esphome.nyra_speaking_ended" in media
    assert "source_id" in media
    assert "${source_id}" in media


def test_speaking_restore_event_requires_actual_announcement_falling_edge():
    text = _speaker_yaml()
    media = text.split("id: external_media_player", 1)[1]
    release = media.split("else:", 1)[1].split("homeassistant.event:", 1)[0]

    # A non-announcement state change must not be confused with playback ending.
    # Release only when an active Nyra announcement has actually stopped.
    assert "not:" in release
    assert "media_player.is_announcing:" in release
    assert "id: external_media_player" in release
    assert "id(nyra_speaking_active)" in release


def test_waveshare_phase_controller_uses_symbolic_phase_substitutions():
    text = _speaker_yaml()
    controller = text.split("id: !remove control_leds", 1)[1].split(
        "- id: nyra_close_feedback_sequence", 1
    )[0]

    expected_cases = (
        "${voice_assist_waiting_for_command_phase_id}",
        "${voice_assist_listening_for_command_phase_id}",
        "${voice_assist_thinking_phase_id}",
        "${voice_assist_replying_phase_id}",
        "${voice_assist_error_phase_id}",
        "${voice_assist_not_ready_phase_id}",
    )
    for phase in expected_cases:
        assert f"case {phase}:" in controller

    for numeric_phase in ("case 2:", "case 3:", "case 4:", "case 5:", "case 10:", "case 11:"):
        assert numeric_phase not in controller


def test_rainbow_comet_keeps_local_color_wheel_cases():
    text = _speaker_yaml()
    rainbow = text.split('name: "nyra_processing_global_rainbow_comet"', 1)[1].split(
        '- addressable_lambda:', 1
    )[0]

    for region in range(5):
        assert f"case {region}:" in rainbow

    assert "${voice_assist_" not in rainbow
