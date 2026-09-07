from __future__ import annotations

import importlib.util
import sys
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


def test_accept_capture_persists_processed_wav_and_metadata(tmp_path):
    wake_words = load_module("wake_words.py", "nyra_ww_accept")
    store = wake_words.WakeWordStore(tmp_path)
    store.initialize()

    created_at = datetime(2026, 9, 6, 9, 30, tzinfo=timezone.utc)
    result = store.complete_capture(
        capture_id="capture-1",
        status="ACCEPTED",
        wake_word_text="  Hey   Nyra  ",
        user_id="user-1",
        source_id="kitchen",
        language="it",
        created_at=created_at,
        processed_audio=ProcessedAudio(b"processed-wav"),
    )

    assert result.status == "ACCEPTED"
    assert result.sample_id is not None

    sample = store.get_sample(result.sample_id)
    assert sample is not None
    assert sample.wake_word_id == "hey nyra"
    assert sample.wake_word_text == "Hey Nyra"
    assert sample.user_id == "user-1"
    assert sample.source_id == "kitchen"
    assert sample.language == "it"
    assert sample.created_at == created_at
    assert sample.preprocessing_version == "prep-1"

    wav_path = Path(sample.wav_path)
    assert wav_path.exists()
    assert wav_path.read_bytes() == b"processed-wav"


def test_arbitrary_new_wake_word_text_is_supported(tmp_path):
    wake_words = load_module("wake_words.py", "nyra_ww_arbitrary")
    store = wake_words.WakeWordStore(tmp_path)
    store.initialize()

    result = store.complete_capture(
        capture_id="capture-2",
        status="ACCEPTED",
        wake_word_text="Gina Casa",
        user_id="user-2",
        source_id="office",
        language="it",
        created_at=datetime(2026, 9, 6, 10, 0, tzinfo=timezone.utc),
        processed_audio=ProcessedAudio(b"wav"),
    )

    sample = store.get_sample(result.sample_id)
    assert sample is not None
    assert sample.wake_word_id == "gina casa"
    assert sample.wake_word_text == "Gina Casa"


def test_rejected_capture_does_not_persist_sample_or_wav(tmp_path):
    wake_words = load_module("wake_words.py", "nyra_ww_rejected")
    store = wake_words.WakeWordStore(tmp_path)
    store.initialize()

    result = store.complete_capture(
        capture_id="capture-3",
        status="REJECTED",
        wake_word_text="Nyra",
        user_id="user-1",
        source_id="bedroom",
        language="it",
        created_at=datetime(2026, 9, 6, 11, 0, tzinfo=timezone.utc),
        processed_audio=ProcessedAudio(b"should-not-persist"),
        reason_code="LOW_SIGNAL",
    )

    assert result.status == "REJECTED"
    assert result.sample_id is None
    assert store.list_samples() == []
    assert list((tmp_path / "wake_words").rglob("*.wav")) == []


def test_failed_capture_does_not_persist_sample_or_wav(tmp_path):
    wake_words = load_module("wake_words.py", "nyra_ww_failed")
    store = wake_words.WakeWordStore(tmp_path)
    store.initialize()

    result = store.complete_capture(
        capture_id="capture-4",
        status="FAILED",
        wake_word_text="Nyra",
        user_id="user-1",
        source_id="bedroom",
        language="it",
        created_at=datetime(2026, 9, 6, 11, 5, tzinfo=timezone.utc),
        processed_audio=None,
        reason_code="PREPROCESSING_FAILED",
    )

    assert result.status == "FAILED"
    assert result.sample_id is None
    assert store.list_samples() == []


def test_one_capture_id_can_create_at_most_one_permanent_sample(tmp_path):
    wake_words = load_module("wake_words.py", "nyra_ww_one_attempt")
    store = wake_words.WakeWordStore(tmp_path)
    store.initialize()

    created_at = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)
    first = store.complete_capture(
        capture_id="capture-once",
        status="ACCEPTED",
        wake_word_text="Nyra",
        user_id="user-1",
        source_id="living-room",
        language="it",
        created_at=created_at,
        processed_audio=ProcessedAudio(b"first"),
    )

    try:
        store.complete_capture(
            capture_id="capture-once",
            status="ACCEPTED",
            wake_word_text="Nyra",
            user_id="user-1",
            source_id="living-room",
            language="it",
            created_at=created_at,
            processed_audio=ProcessedAudio(b"second"),
        )
    except wake_words.CaptureAlreadyCompleted:
        pass
    else:
        raise AssertionError("second completion of the same capture_id must fail")

    samples = store.list_samples()
    assert len(samples) == 1
    assert samples[0].sample_id == first.sample_id
    assert Path(samples[0].wav_path).read_bytes() == b"first"


def test_query_is_newest_first_and_can_filter_by_normalized_identity(tmp_path):
    wake_words = load_module("wake_words.py", "nyra_ww_query")
    store = wake_words.WakeWordStore(tmp_path)
    store.initialize()

    fixtures = [
        ("c1", "Nyra", "2026-09-06T08:00:00+00:00", b"a"),
        ("c2", "Gina", "2026-09-06T10:00:00+00:00", b"b"),
        ("c3", "  NYRA ", "2026-09-06T09:00:00+00:00", b"c"),
    ]
    for capture_id, text, timestamp, wav in fixtures:
        store.complete_capture(
            capture_id=capture_id,
            status="ACCEPTED",
            wake_word_text=text,
            user_id="u",
            source_id="s",
            language="it",
            created_at=datetime.fromisoformat(timestamp),
            processed_audio=ProcessedAudio(wav),
        )

    all_samples = store.list_samples()
    assert [sample.capture_id for sample in all_samples] == ["c2", "c3", "c1"]

    nyra = store.list_samples(wake_word_id="nyra")
    assert [sample.capture_id for sample in nyra] == ["c3", "c1"]


def test_delete_single_and_multiple_remove_rows_and_wavs(tmp_path):
    wake_words = load_module("wake_words.py", "nyra_ww_delete")
    store = wake_words.WakeWordStore(tmp_path)
    store.initialize()

    sample_ids = []
    paths = []
    for index in range(3):
        result = store.complete_capture(
            capture_id=f"capture-{index}",
            status="ACCEPTED",
            wake_word_text="Nyra",
            user_id="u",
            source_id="s",
            language="it",
            created_at=datetime(2026, 9, 6, 13, index, tzinfo=timezone.utc),
            processed_audio=ProcessedAudio(f"wav-{index}".encode()),
        )
        sample_ids.append(result.sample_id)
        paths.append(Path(store.get_sample(result.sample_id).wav_path))

    assert store.delete_sample(sample_ids[0]) is True
    assert not paths[0].exists()

    deleted = store.delete_samples(sample_ids[1:])
    assert deleted == 2
    assert store.list_samples() == []
    assert all(not path.exists() for path in paths)


def test_dataset_count_is_grouped_by_normalized_wake_word(tmp_path):
    wake_words = load_module("wake_words.py", "nyra_ww_count")
    store = wake_words.WakeWordStore(tmp_path)
    store.initialize()
    for index, text in enumerate(("Nyra", " NYRA ", "Gina")):
        store.complete_capture(
            capture_id=f"count-{index}", status="ACCEPTED", wake_word_text=text,
            user_id="u", source_id="s", language="it",
            created_at=datetime(2026, 9, 6, 14, index, tzinfo=timezone.utc),
            processed_audio=ProcessedAudio(b"wav"),
        )

    assert store.count_samples("nyra") == 2
    assert store.count_samples("gina") == 1


def test_wake_word_sample_exposes_duration_and_quality_for_admin(tmp_path):
    wake_words = load_module("wake_words.py", "nyra_ww_admin_metadata")
    store = wake_words.WakeWordStore(tmp_path)
    store.initialize()

    processed = ProcessedAudio(b"wav")
    object.__setattr__(processed, "duration_seconds", 1.2)
    object.__setattr__(processed, "quality", {"rms": 0.2})
    result = store.complete_capture(
        capture_id="admin-1", status="ACCEPTED", wake_word_text="Nyra",
        user_id="u", source_id="nyra-mansarda", language="it",
        created_at=datetime(2026, 9, 7, 18, 0, tzinfo=timezone.utc),
        processed_audio=processed,
    )

    sample = store.get_sample(result.sample_id)
    assert sample.duration_seconds == 1.2
    assert sample.quality == {"rms": 0.2}
