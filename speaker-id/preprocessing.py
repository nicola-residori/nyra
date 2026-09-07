from __future__ import annotations

import io
import math
import wave
from dataclasses import dataclass
from typing import Literal


TARGET_SAMPLE_RATE = 16000
MODEL_MIN_SECONDS = 1.0
MIN_REAL_SPEECH_FOR_IDENTIFICATION = 0.25
MIN_REAL_SPEECH_FOR_ENROLLMENT = 0.35
MIN_REAL_SPEECH_FOR_WAKE_WORD = 0.15
ENROLLMENT_MIN_RMS = 0.0015
SPEECH_ACTIVITY_THRESHOLD = 0.003
PREPROCESSING_VERSION = "1"


@dataclass(frozen=True)
class AudioQuality:
    rms: float
    peak: float
    clipping_ratio: float
    snr_db: float | None


@dataclass(frozen=True)
class ProcessedAudio:
    wav_bytes: bytes
    sample_rate: int
    duration_seconds: float
    speech_seconds: float
    quality: AudioQuality
    preprocessing_version: str


class AudioRejected(ValueError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def preprocess_audio(
    raw: bytes,
    *,
    mode: Literal["identification", "enrollment", "wake_word"],
) -> ProcessedAudio:
    if mode not in {"identification", "enrollment", "wake_word"}:
        raise ValueError(f"unsupported preprocessing mode: {mode}")

    samples, source_rate = _decode_wav(raw)
    mono = _to_mono(samples)
    resampled = _resample(mono, source_rate)

    trimmed, speech_seconds = _trim_to_signal(resampled)
    quality = _quality(trimmed)
    if mode == "enrollment" and quality.rms < ENROLLMENT_MIN_RMS:
        raise AudioRejected("LOW_SIGNAL")

    minimum_real_speech = {
        "identification": MIN_REAL_SPEECH_FOR_IDENTIFICATION,
        "enrollment": MIN_REAL_SPEECH_FOR_ENROLLMENT,
        "wake_word": MIN_REAL_SPEECH_FOR_WAKE_WORD,
    }[mode]

    if speech_seconds < minimum_real_speech:
        raise AudioRejected("TOO_SHORT")

    normalized = _normalize(trimmed)
    padded = _pad_for_model(normalized)
    wav_bytes = _encode_wav(padded)
    duration_seconds = len(padded) / TARGET_SAMPLE_RATE

    return ProcessedAudio(
        wav_bytes=wav_bytes,
        sample_rate=TARGET_SAMPLE_RATE,
        duration_seconds=duration_seconds,
        speech_seconds=speech_seconds,
        quality=quality,
        preprocessing_version=PREPROCESSING_VERSION,
    )


def _decode_wav(raw: bytes) -> tuple[list[list[int]], int]:
    try:
        with wave.open(io.BytesIO(raw), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError) as exc:
        raise AudioRejected("INVALID_AUDIO") from exc

    if sample_width != 2:
        raise AudioRejected("UNSUPPORTED_SAMPLE_WIDTH")
    if channels not in {1, 2}:
        raise AudioRejected("UNSUPPORTED_CHANNELS")
    if sample_rate <= 0:
        raise AudioRejected("INVALID_SAMPLE_RATE")
    if len(frames) % (2 * channels):
        raise AudioRejected("INVALID_AUDIO")

    decoded = [[] for _ in range(channels)]
    frame_size = 2 * channels
    for offset in range(0, len(frames), frame_size):
        for channel in range(channels):
            start = offset + channel * 2
            value = int.from_bytes(frames[start:start + 2], "little", signed=True)
            decoded[channel].append(value)

    return decoded, sample_rate


def _to_mono(channels: list[list[int]]) -> list[int]:
    if not channels or not channels[0]:
        raise AudioRejected("NO_AUDIO")
    if len(channels) == 1:
        return channels[0]

    left, right = channels
    return [int((a + b) / 2) for a, b in zip(left, right)]


def _resample(samples: list[int], source_rate: int) -> list[int]:
    if source_rate == TARGET_SAMPLE_RATE:
        return samples
    if not samples:
        return []

    output_length = max(1, round(len(samples) * TARGET_SAMPLE_RATE / source_rate))
    ratio = source_rate / TARGET_SAMPLE_RATE
    output: list[int] = []

    for index in range(output_length):
        source_position = index * ratio
        left_index = min(int(source_position), len(samples) - 1)
        right_index = min(left_index + 1, len(samples) - 1)
        fraction = source_position - left_index
        value = samples[left_index] * (1.0 - fraction) + samples[right_index] * fraction
        output.append(int(round(value)))

    return output


def _trim_to_signal(samples: list[int]) -> tuple[list[int], float]:
    threshold = int(32767 * SPEECH_ACTIVITY_THRESHOLD)
    active = [index for index, value in enumerate(samples) if abs(value) >= threshold]

    if not active:
        return samples, 0.0

    margin = int(TARGET_SAMPLE_RATE * 0.02)
    start = max(0, active[0] - margin)
    end = min(len(samples), active[-1] + margin + 1)
    trimmed = samples[start:end]

    speech_seconds = len(trimmed) / TARGET_SAMPLE_RATE
    return trimmed, speech_seconds


def _quality(samples: list[int]) -> AudioQuality:
    if not samples:
        return AudioQuality(rms=0.0, peak=0.0, clipping_ratio=0.0, snr_db=None)

    normalized = [value / 32768.0 for value in samples]
    square_mean = sum(value * value for value in normalized) / len(normalized)
    rms = math.sqrt(square_mean)
    peak = max(abs(value) for value in normalized)

    clipping_ratio = (
        sum(1 for value in normalized if abs(value) >= 0.995) / len(normalized)
    )

    noise_candidates = sorted(abs(value) for value in normalized)
    noise_window = max(1, len(noise_candidates) // 10)
    noise_rms = math.sqrt(
        sum(value * value for value in noise_candidates[:noise_window]) / noise_window
    )

    if rms <= 0:
        snr_db = None
    elif noise_rms <= 1e-9:
        snr_db = 60.0
    else:
        snr_db = 20.0 * math.log10(rms / noise_rms)

    return AudioQuality(
        rms=rms,
        peak=peak,
        clipping_ratio=clipping_ratio,
        snr_db=snr_db,
    )


def _normalize(samples: list[int]) -> list[int]:
    if not samples:
        return samples

    peak = max(abs(value) for value in samples)
    if peak <= 0:
        return samples

    target_peak = int(32767 * 0.90)
    gain = min(target_peak / peak, 8.0)

    if gain <= 1.0:
        return samples

    return [
        max(-32768, min(32767, int(round(value * gain))))
        for value in samples
    ]


def _pad_for_model(samples: list[int]) -> list[int]:
    minimum_frames = int(MODEL_MIN_SECONDS * TARGET_SAMPLE_RATE)
    if len(samples) >= minimum_frames:
        return samples
    return samples + [0] * (minimum_frames - len(samples))


def _encode_wav(samples: list[int]) -> bytes:
    pcm = bytearray()
    for value in samples:
        pcm.extend(int(value).to_bytes(2, "little", signed=True))

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(TARGET_SAMPLE_RATE)
        wav.writeframes(bytes(pcm))
    return buffer.getvalue()
