from __future__ import annotations

import io
import json
import tarfile
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Protocol


class WakeWordSampleLike(Protocol):
    sample_id: str
    capture_id: str
    wake_word_id: str
    wake_word_text: str
    user_id: str
    source_id: str
    language: str
    created_at: object
    preprocessing_version: str
    wav_path: str


class WakeWordStoreLike(Protocol):
    def get_sample(self, sample_id: str) -> WakeWordSampleLike | None: ...


class UnknownWakeWordSample(ValueError):
    def __init__(self, sample_ids: list[str]):
        super().__init__(f"unknown wake word sample ids: {', '.join(sample_ids)}")
        self.sample_ids = sample_ids


def export_samples(store: WakeWordStoreLike, sample_ids: Iterable[str]) -> bytes:
    ordered_ids = list(sample_ids)
    samples = []
    missing = []

    for sample_id in ordered_ids:
        sample = store.get_sample(sample_id)
        if sample is None:
            missing.append(sample_id)
        else:
            samples.append(sample)

    if missing:
        raise UnknownWakeWordSample(missing)

    metadata = {
        "samples": [
            {
                "sample_id": sample.sample_id,
                "capture_id": sample.capture_id,
                "wake_word_id": sample.wake_word_id,
                "wake_word_text": sample.wake_word_text,
                "user_id": sample.user_id,
                "source_id": sample.source_id,
                "language": sample.language,
                "created_at": sample.created_at.isoformat(),
                "preprocessing_version": sample.preprocessing_version,
            }
            for sample in samples
        ]
    }

    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        metadata_bytes = json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        metadata_info = tarfile.TarInfo("metadata.json")
        metadata_info.size = len(metadata_bytes)
        tar.addfile(metadata_info, io.BytesIO(metadata_bytes))

        for sample in samples:
            wav_bytes = Path(sample.wav_path).read_bytes()
            info = tarfile.TarInfo(f"audio/{sample.sample_id}.wav")
            info.size = len(wav_bytes)
            tar.addfile(info, io.BytesIO(wav_bytes))

    return output.getvalue()
