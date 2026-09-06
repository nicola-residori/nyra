from __future__ import annotations

import importlib.util
import io
import math
import struct
import sys
import wave
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).parents[2] / "speaker-id" / "preprocessing.py"


def load_module():
    spec = importlib.util.spec_from_file_location("nyra_speaker_id_preprocessing", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_wav(
    *,
    sample_rate: int = 8000,
    channels: int = 2,
    duration_seconds: float = 0.45,
    tone_hz: float = 440.0,
    amplitude: float = 0.35,
    silence_prefix: float = 0.08,
    silence_suffix: float = 0.08,
) -> bytes:
    total_frames = int(sample_rate * duration_seconds)
    prefix_frames = int(sample_rate * silence_prefix)
    suffix_frames = int(sample_rate * silence_suffix)
    speech_end = total_frames - suffix_frames

    frames = bytearray()
    for index in range(total_frames):
        if prefix_frames <= index < speech_end:
            sample = amplitude * math.sin(2.0 * math.pi * tone_hz * index / sample_rate)
        else:
            sample = 0.0
        value = max(-32768, min(32767, int(sample * 32767)))

        for _ in range(channels):
            frames.extend(struct.pack("<h", value))

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(frames))
    return buffer.getvalue()


def read_wav_header(raw: bytes):
    with wave.open(io.BytesIO(raw), "rb") as wav:
        return {
            "channels": wav.getnchannels(),
            "sample_width": wav.getsampwidth(),
            "sample_rate": wav.getframerate(),
            "frames": wav.getnframes(),
        }


def test_output_is_canonical_mono_16khz():
    module = load_module()
    raw = make_wav(sample_rate=8000, channels=2)

    result = module.preprocess_audio(raw, mode="identification")
    header = read_wav_header(result.wav_bytes)

    assert header["channels"] == 1
    assert header["sample_width"] == 2
    assert header["sample_rate"] == 16000
    assert result.sample_rate == 16000


def test_short_valid_identification_is_processable():
    module = load_module()
    raw = make_wav(duration_seconds=0.42, silence_prefix=0.05, silence_suffix=0.05)

    result = module.preprocess_audio(raw, mode="identification")

    assert result.speech_seconds >= module.MIN_REAL_SPEECH_FOR_IDENTIFICATION


def test_model_padding_does_not_count_as_real_speech():
    module = load_module()
    raw = make_wav(duration_seconds=0.42, silence_prefix=0.05, silence_suffix=0.05)

    result = module.preprocess_audio(raw, mode="identification")

    assert result.duration_seconds >= module.MODEL_MIN_SECONDS
    assert result.speech_seconds < result.duration_seconds


def test_silence_is_trimmed_before_model_padding():
    module = load_module()
    raw = make_wav(
        duration_seconds=0.9,
        silence_prefix=0.25,
        silence_suffix=0.25,
    )

    result = module.preprocess_audio(raw, mode="identification")

    assert result.speech_seconds < 0.55
    assert result.speech_seconds > 0.25


def test_quality_contains_signal_metadata():
    module = load_module()
    raw = make_wav()

    result = module.preprocess_audio(raw, mode="identification")

    assert result.quality.rms > 0
    assert 0 < result.quality.peak <= 1.0
    assert 0.0 <= result.quality.clipping_ratio <= 1.0
    assert result.quality.snr_db is not None
    assert result.preprocessing_version


def test_bad_enrollment_audio_is_rejected():
    module = load_module()
    raw = make_wav(amplitude=0.001)

    with pytest.raises(module.AudioRejected) as exc:
        module.preprocess_audio(raw, mode="enrollment")

    assert exc.value.reason_code == "LOW_SIGNAL"


def test_identification_gate_is_less_strict_than_enrollment():
    module = load_module()
    raw = make_wav(amplitude=0.01)

    identification = module.preprocess_audio(raw, mode="identification")
    assert identification.speech_seconds >= module.MIN_REAL_SPEECH_FOR_IDENTIFICATION

    with pytest.raises(module.AudioRejected):
        module.preprocess_audio(raw, mode="enrollment")


def test_invalid_mode_is_rejected():
    module = load_module()
    raw = make_wav()

    with pytest.raises(ValueError):
        module.preprocess_audio(raw, mode="invalid")
