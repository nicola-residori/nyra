from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]

def load_module(filename: str, name: str):
    path = ROOT / "speaker-id" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class FakeQuality:
    rms: float = 0.2
    peak: float = 0.8
    clipping_ratio: float = 0.0
    snr_db: float | None = 30.0


@dataclass(frozen=True)
class FakeProcessedAudio:
    wav_bytes: bytes = b"processed-wav"
    sample_rate: int = 16000
    duration_seconds: float = 1.0
    speech_seconds: float = 0.6
    quality: FakeQuality = FakeQuality()
    preprocessing_version: str = "test-v1"


class FakeEngine:
    def __init__(self, embedding=None, error=None):
        self.embedding = embedding or [0.25, 0.75]
        self.error = error

    def embed(self, audio):
        if self.error is not None:
            raise self.error
        return list(self.embedding)


def test_enrollment_persists_processed_wav_embedding_and_quality(tmp_path):
    profiles = load_module("profiles.py", "nyra_speaker_profiles_enroll")
    enrollment = load_module("enrollment.py", "nyra_speaker_enrollment_ok")
    store = profiles.ProfileStore(tmp_path)
    store.initialize()

    result = enrollment.accept_enrollment_sample(
        store=store,
        engine=FakeEngine(),
        user_id="canonical-user",
        source_id="office",
        processed_audio=FakeProcessedAudio(),
    )

    assert result.status == "ACCEPTED"
    sample = store.list_samples("canonical-user")[0]
    assert Path(sample.wav_path).read_bytes() == b"processed-wav"
    assert sample.embedding == [0.25, 0.75]
    assert sample.quality["rms"] == 0.2
    assert sample.preprocessing_version == "test-v1"
    assert store.get_profile("canonical-user").centroid == [0.25, 0.75]


def test_embedding_failure_leaves_no_profile_sample_or_file(tmp_path):
    profiles = load_module("profiles.py", "nyra_speaker_profiles_embedfail")
    enrollment = load_module("enrollment.py", "nyra_speaker_enrollment_embedfail")
    store = profiles.ProfileStore(tmp_path)
    store.initialize()

    with pytest.raises(RuntimeError, match="embedding failed"):
        enrollment.accept_enrollment_sample(
            store=store,
            engine=FakeEngine(error=RuntimeError("embedding failed")),
            user_id="u",
            source_id="speaker",
            processed_audio=FakeProcessedAudio(),
        )

    assert store.get_profile("u") is None
    assert store.list_samples("u") == []
    assert list((tmp_path / "samples").rglob("*.wav")) == []


def test_database_failure_rolls_back_written_processed_wav(tmp_path, monkeypatch):
    profiles = load_module("profiles.py", "nyra_speaker_profiles_dbfail")
    enrollment = load_module("enrollment.py", "nyra_speaker_enrollment_dbfail")
    store = profiles.ProfileStore(tmp_path)
    store.initialize()

    original = store._insert_sample_metadata

    def fail_after_insert(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("database failed")

    monkeypatch.setattr(store, "_insert_sample_metadata", fail_after_insert)

    with pytest.raises(RuntimeError, match="database failed"):
        enrollment.accept_enrollment_sample(
            store=store,
            engine=FakeEngine(),
            user_id="u",
            source_id=None,
            processed_audio=FakeProcessedAudio(),
        )

    assert store.get_profile("u") is None
    assert store.list_samples("u") == []
    assert list((tmp_path / "samples").rglob("*.wav")) == []
