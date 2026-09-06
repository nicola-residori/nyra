from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol


class EmbeddingEngine(Protocol):
    def embed(self, audio: Any) -> list[float]:
        ...


@dataclass(frozen=True)
class EnrollmentResult:
    status: str
    sample_id: str
    user_id: str


def accept_enrollment_sample(
    *,
    store,
    engine: EmbeddingEngine,
    user_id: str,
    source_id: str | None,
    processed_audio,
) -> EnrollmentResult:
    embedding = engine.embed(processed_audio)
    quality = asdict(processed_audio.quality)

    sample = store.add_sample(
        user_id=user_id,
        source_id=source_id,
        wav_bytes=processed_audio.wav_bytes,
        embedding=embedding,
        quality=quality,
        preprocessing_version=processed_audio.preprocessing_version,
    )

    return EnrollmentResult(
        status="ACCEPTED",
        sample_id=sample.sample_id,
        user_id=sample.user_id,
    )
