from __future__ import annotations

import importlib.util
import io
import json
import sys
import tarfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


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
class ProcessedAudio:
    wav_bytes: bytes
    preprocessing_version: str = "prep-1"


def create_sample(store, *, capture_id: str, text: str, minute: int, wav: bytes):
    return store.complete_capture(
        capture_id=capture_id,
        status="ACCEPTED",
        wake_word_text=text,
        user_id="user-1",
        source_id="kitchen",
        language="it",
        created_at=datetime(2026, 9, 6, 14, minute, tzinfo=timezone.utc),
        processed_audio=ProcessedAudio(wav),
    )


def test_tar_gz_export_contains_exact_members_and_matching_metadata(tmp_path):
    wake_words = load_module("wake_words.py", "nyra_ww_export_store")
    exporter_module = load_module("wake_word_export.py", "nyra_ww_export")

    store = wake_words.WakeWordStore(tmp_path)
    store.initialize()

    one = create_sample(store, capture_id="c1", text="Nyra", minute=1, wav=b"one")
    two = create_sample(store, capture_id="c2", text="Gina", minute=2, wav=b"two")
    create_sample(store, capture_id="c3", text="Ignore Me", minute=3, wav=b"three")

    archive = exporter_module.export_samples(store, [two.sample_id, one.sample_id])

    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        members = tar.getnames()
        assert members == [
            "metadata.json",
            f"audio/{two.sample_id}.wav",
            f"audio/{one.sample_id}.wav",
        ]

        metadata = json.load(tar.extractfile("metadata.json"))
        assert [item["sample_id"] for item in metadata["samples"]] == [
            two.sample_id,
            one.sample_id,
        ]

        assert tar.extractfile(f"audio/{two.sample_id}.wav").read() == b"two"
        assert tar.extractfile(f"audio/{one.sample_id}.wav").read() == b"one"

    assert metadata["samples"][0]["wake_word_id"] == "gina"
    assert metadata["samples"][0]["wake_word_text"] == "Gina"
    assert metadata["samples"][0]["user_id"] == "user-1"
    assert metadata["samples"][0]["source_id"] == "kitchen"
    assert metadata["samples"][0]["language"] == "it"
    assert metadata["samples"][0]["preprocessing_version"] == "prep-1"


def test_export_fails_if_any_explicit_sample_id_is_missing(tmp_path):
    wake_words = load_module("wake_words.py", "nyra_ww_export_missing_store")
    exporter_module = load_module("wake_word_export.py", "nyra_ww_export_missing")

    store = wake_words.WakeWordStore(tmp_path)
    store.initialize()
    sample = create_sample(store, capture_id="c1", text="Nyra", minute=1, wav=b"one")

    try:
        exporter_module.export_samples(store, [sample.sample_id, "missing-id"])
    except exporter_module.UnknownWakeWordSample as exc:
        assert exc.sample_ids == ["missing-id"]
    else:
        raise AssertionError("export must fail instead of producing a partial archive")
