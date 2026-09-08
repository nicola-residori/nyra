from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "esphome/packages/nyra-speaker.yaml"
ENROLLMENT_PACKAGE = ROOT / "esphome/packages/nyra-enrollment.yaml"
COMPONENT = ROOT / "esphome/components/nyra_audio_ingress"
VENDORED_WAVESHARE_CORE = ROOT / "esphome/vendor/waveshare-esp32-s3-audio-va-v1.0.0-core.yaml"


def test_enrollment_overlay_streams_the_existing_microphone_only_to_home_assistant():
    text = ENROLLMENT_PACKAGE.read_text(encoding="utf-8")

    assert "nyra_audio_ingress:" in text
    assert "microphone: i2s_mics" in text
    assert "url: ${nyra_audio_ingress_url}" in text
    assert "token: !secret nyra_ingress_token" in text
    assert 'source_id: "${source_id}"' in text
    assert 'language: "${nyra_language}"' in text
    assert "/api/nyra/audio" in text
    assert "nyra-speaker-id" not in text.lower()


def test_enrollment_overlay_uses_mansarda_measured_voice_activity_levels():
    text = ENROLLMENT_PACKAGE.read_text(encoding="utf-8")

    assert "speech_rms: 45" in text
    assert "continuation_rms: 20" in text
    assert "speech_on: 100ms" in text
    assert "trailing_silence: 900ms" in text


def test_identification_captures_the_complete_clean_assist_listening_window():
    text = ENROLLMENT_PACKAGE.read_text(encoding="utf-8")
    voice = text.split("voice_assistant:", 1)[1]

    listening = voice.split("on_listening:", 1)[1].split("on_stt_vad_start:", 1)[0]
    assert "start_identification_stream();" in listening
    vad_start = voice.split("on_stt_vad_start:", 1)[1].split("on_stt_vad_end:", 1)[0] if "on_stt_vad_start:" in voice else ""
    assert "start_identification_stream();" not in vad_start
    vad_end = voice.split("on_stt_vad_end:", 1)[1].split("button:", 1)[0]
    assert "end_stream();" in vad_end


def test_wake_cue_finishes_before_assist_starts():
    package = PACKAGE.read_text(encoding="utf-8")
    core = VENDORED_WAVESHARE_CORE.read_text(encoding="utf-8")

    assert "../vendor/waveshare-esp32-s3-audio-va-v1.0.0-core.yaml" in package
    wake = core.split("# Otherwise: beep, then start Assist.", 1)[1].split("voice_assistant:", 1)[0]
    assert "delay: 1000ms" in wake
    assert "delay: 300ms" not in wake
    assert wake.index("delay: 1000ms") < wake.index("voice_assistant.start:")


def test_wake_detection_shows_listening_white_before_the_clean_audio_delay():
    core = VENDORED_WAVESHARE_CORE.read_text(encoding="utf-8")
    wake = core.split("# Otherwise: beep, then start Assist.", 1)[1].split(
        "voice_assistant:", 1
    )[0]

    assert "light.turn_on:" in wake
    assert "id: status_ring" in wake
    assert 'effect: "Pulse Fast"' in wake
    assert "red: 100%" in wake
    assert "green: 100%" in wake
    assert "blue: 100%" in wake
    assert wake.index("light.turn_on:") < wake.index("delay: 1000ms")


def test_stable_speaker_package_cannot_enable_experimental_enrollment():
    text = PACKAGE.read_text(encoding="utf-8")

    assert "nyra_audio_ingress" not in text
    assert "nyra_enrollment_capture" not in text
    assert "start_identification_stream" not in text


def test_audio_tee_preserves_the_existing_listening_visual_sequence():
    text = PACKAGE.read_text(encoding="utf-8")
    voice = text.split("voice_assistant:", 1)[1].split("media_player:", 1)[0]
    on_listening = voice.split("on_listening:", 1)[1].split("on_stt_vad_start:", 1)[0]

    assert 'effect: "Pulse Fast"' in on_listening
    assert 'effect: "nyra_listening_white_fast"' not in on_listening


def test_component_uses_multiple_listener_callback_and_bounded_backpressure():
    header = (COMPONENT / "nyra_audio_ingress.h").read_text(encoding="utf-8")
    source = (COMPONENT / "nyra_audio_ingress.cpp").read_text(encoding="utf-8")

    assert "microphone::MicrophoneSource" in header
    assert "add_data_callback" in source
    assert "MAX_QUEUED_AUDIO_BYTES" in header
    assert "MAX_RESPONSE_BYTES" in header
    assert "awaiting_chunk_ack_" in header
    assert "esp_websocket_client_send_bin" in source
    assert "WEBSOCKET_TRANSPORT_OVER_TCP" in source
    assert "disable_auto_reconnect = true" in source
    assert "WS_TRANSPORT_OPCODES_CONT" in source
    assert "response_queue_.size() >= MAX_RESPONSE_QUEUE" in source


def test_transport_batches_microphone_callbacks_to_keep_up_with_realtime_audio():
    header = (COMPONENT / "nyra_audio_ingress.h").read_text(encoding="utf-8")
    source = (COMPONENT / "nyra_audio_ingress.cpp").read_text(encoding="utf-8")

    assert "MAX_TRANSPORT_CHUNK_BYTES = 16 * 1024" in header
    assert "MAX_QUEUED_AUDIO_BYTES = 64 * 1024" in header
    send = source.split("ChunkQueueResult NyraAudioIngress::send_next_chunk_()", 1)[1].split(
        "bool NyraAudioIngress::queue_transport_command_", 1
    )[0]
    assert "audio_source_->fill" in send
    assert "command.binary.assign" in send


def test_microphone_callback_only_writes_to_a_preallocated_ring_buffer():
    source = (COMPONENT / "nyra_audio_ingress.cpp").read_text(encoding="utf-8")
    callback = source.split("void NyraAudioIngress::on_microphone_data_", 1)[1].split(
        "void NyraAudioIngress::websocket_event_", 1
    )[0]

    assert "write_without_replacement" in callback
    assert "push_back" not in callback
    assert "xSemaphoreTake" not in callback
    assert "vad_.update" not in callback


def test_microphone_tee_is_passive_and_rejects_non_16khz_sources():
    codegen = (COMPONENT / "__init__.py").read_text(encoding="utf-8")

    assert "microphone_source_to_code(config[CONF_MICROPHONE], passive=True)" in codegen
    assert "final_validate_microphone_source_schema" in codegen
    assert "sample_rate=16000" in codegen


def test_websocket_transport_never_blocks_the_esphome_loop():
    header = (COMPONENT / "nyra_audio_ingress.h").read_text(encoding="utf-8")
    source = (COMPONENT / "nyra_audio_ingress.cpp").read_text(encoding="utf-8")
    loop_body = source.split("void NyraAudioIngress::loop()", 1)[1].split(
        "void NyraAudioIngress::handle_response_", 1
    )[0]

    assert "TaskHandle_t transport_task_" in header
    assert "xTaskCreate" in source
    assert "esp_websocket_client_start" not in loop_body
    assert "esp_websocket_client_send_text" not in loop_body
    assert "esp_websocket_client_send_bin" not in loop_body
    assert "esp_websocket_client_stop" not in loop_body
    assert "esp_websocket_client_destroy" not in loop_body
    assert "send_failed_event_" in header


def test_response_frames_are_reassembled_only_after_the_final_fragment():
    header = (COMPONENT / "nyra_audio_ingress.h").read_text(encoding="utf-8")
    source = (COMPONENT / "nyra_audio_ingress.cpp").read_text(encoding="utf-8")

    assert "receiving_text_message_" in header
    assert "data->payload_offset == 0" in source
    assert "data->fin" in source
    assert "WEBSOCKET_EVENT_CLOSED" in source


def test_configuration_rejects_wss_until_trusted_ca_support_exists():
    codegen = (COMPONENT / "__init__.py").read_text(encoding="utf-8")

    assert 'startswith("ws://")' in codegen
    assert '"wss://"' not in codegen


def test_terminal_result_wins_over_the_following_clean_socket_close():
    source = (COMPONENT / "nyra_audio_ingress.cpp").read_text(encoding="utf-8")
    loop_body = source.split("void NyraAudioIngress::loop()", 1)[1].split(
        "void NyraAudioIngress::handle_response_", 1
    )[0]

    assert loop_body.index("take_response_") < loop_body.index("disconnected_event_")


def test_new_stream_waits_for_transport_teardown_acknowledgement():
    header = (COMPONENT / "nyra_audio_ingress.h").read_text(encoding="utf-8")
    source = (COMPONENT / "nyra_audio_ingress.cpp").read_text(encoding="utf-8")

    assert "CLOSING" in header
    assert "transport_closed_event_" in header
    assert "state_ = StreamState::CLOSING" in source
    assert "complete_finish_" in source


def test_audio_tee_does_not_override_existing_sounds_or_add_feedback_cues():
    text = ENROLLMENT_PACKAGE.read_text(encoding="utf-8")

    assert "id: !extend wake_word_triggered_sound" not in text
    assert "nyra_bip.wav" not in text
    assert "nyra_ok.wav" not in text
    assert "nyra_ko.wav" not in text
    assert "sound_file:" not in text


def test_enrollment_button_owns_direct_microphone_capture_and_restores_wake_word():
    text = ENROLLMENT_PACKAGE.read_text(encoding="utf-8")
    ingress = text.split("nyra_audio_ingress:", 1)[1].split("text_sensor:", 1)[0]
    buttons = text.split("button:", 1)[1].split("micro_wake_word:", 1)[0]

    assert 'name: "Nyra Enrollment Capture"' in buttons
    assert "micro_wake_word.stop:" in buttons
    stop_sequence = buttons.split("micro_wake_word.stop:", 1)[1].split("start_enrollment_capture();", 1)[0]
    assert "wait_until:" in stop_sequence
    assert "micro_wake_word.is_running:" in stop_sequence
    assert "microphone.capture: i2s_mics" in buttons
    assert "start_enrollment_capture();" in buttons
    assert 'effect: "nyra_listening_white_fast"' in buttons
    assert "on_accepted:" in ingress
    assert "on_rejected:" in ingress
    assert "on_failed:" in ingress
    assert ingress.count("microphone.stop_capture: i2s_mics") == 3
    assert ingress.count("micro_wake_word.start:") == 3
    assert 'effect: "nyra_identity_green_2blink"' in ingress
    assert ingress.count('effect: "nyra_identity_red_2blink"') == 2


def test_component_has_a_dedicated_vad_bounded_enrollment_capture_mode():
    header = (COMPONENT / "nyra_audio_ingress.h").read_text(encoding="utf-8")
    source = (COMPONENT / "nyra_audio_ingress.cpp").read_text(encoding="utf-8")

    assert "start_identification_stream" in header
    assert "start_enrollment_capture" in header
    assert "VoiceActivityDetector" in header
    assert '"ENROLLMENT_CAPTURE"' in source
    assert 'root["purpose"] = this->capture_purpose_' in source
    assert "CaptureDecision::COMPLETE" in source
    assert "CaptureDecision::NO_SPEECH_TIMEOUT" in source


def test_overlapping_enrollment_capture_reports_failure_for_cleanup():
    source = (COMPONENT / "nyra_audio_ingress.cpp").read_text(encoding="utf-8")

    overlap_guard = source.split("if (this->state_ != StreamState::IDLE)", 1)[1].split("}", 1)[0]
    assert "enrollment_capture" in overlap_guard
    assert "failed_callbacks_.call()" in overlap_guard


def test_vad_defaults_are_exposed_through_esphome_codegen():
    codegen = (COMPONENT / "__init__.py").read_text(encoding="utf-8")

    assert 'CONF_SPEECH_RMS = "speech_rms"' in codegen
    assert 'CONF_CONTINUATION_RMS = "continuation_rms"' in codegen
    assert 'CONF_SPEECH_ON = "speech_on"' in codegen
    assert 'CONF_TRAILING_SILENCE = "trailing_silence"' in codegen
    assert 'CONF_NO_SPEECH_TIMEOUT = "no_speech_timeout"' in codegen
    assert 'CONF_MAX_CAPTURE_DURATION = "max_capture_duration"' in codegen
    assert "default=700" in codegen
    assert "default=450" in codegen
    assert 'default="120ms"' in codegen
    assert 'default="900ms"' in codegen
    assert 'default="8s"' in codegen
    assert 'default="15s"' in codegen
    assert "set_speech_rms" in codegen
    assert "set_continuation_rms" in codegen
    assert "set_speech_on_ms" in codegen
    assert "set_trailing_silence_ms" in codegen
    assert "set_no_speech_timeout_ms" in codegen
    assert "set_max_capture_duration_ms" in codegen


def test_enrollment_result_status_uses_existing_terminal_callbacks():
    source = (COMPONENT / "nyra_audio_ingress.cpp").read_text(encoding="utf-8")

    assert 'root["result"]["status"]' in source
    assert 'status == "ACCEPTED"' in source
    assert 'status == "REJECTED"' in source


def test_overlay_has_separate_wake_word_dataset_capture_button():
    text = ENROLLMENT_PACKAGE.read_text(encoding="utf-8")

    assert 'name: "Nyra Wake Word Capture"' in text
    assert "start_wake_word_capture();" in text


def test_new_speaker_template_inherits_shared_ingress_configuration():
    example = (ROOT / "esphome/devices/nyra-speaker.example.yaml").read_text(
        encoding="utf-8"
    )
    secrets = (ROOT / "esphome/secrets.example.yaml").read_text(encoding="utf-8")

    assert "nyra_audio_ingress_url" not in example
    assert "nyra_language" not in example
    assert "nyra_ingress_token:" in secrets
    assert "speaker-id" not in example.lower()
