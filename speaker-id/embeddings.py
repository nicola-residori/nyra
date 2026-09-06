from __future__ import annotations

import io
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from preprocessing import ProcessedAudio


class SpeakerEmbeddingEngine(Protocol):
    def embed(self, audio: "ProcessedAudio") -> list[float]:
        ...


class SpeechBrainECAPAEngine:
    """Lazy production adapter around SpeechBrain ECAPA-TDNN."""

    def __init__(self, *, savedir: str | None = None):
        self._savedir = savedir
        self._classifier = None

    def _load(self):
        if self._classifier is None:
            try:
                from speechbrain.inference.speaker import EncoderClassifier
            except ImportError as exc:
                raise RuntimeError(
                    "SpeechBrain is required for production ECAPA embeddings"
                ) from exc

            kwargs = {}
            if self._savedir is not None:
                kwargs["savedir"] = self._savedir
            self._classifier = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                **kwargs,
            )
        return self._classifier

    def embed(self, audio: "ProcessedAudio") -> list[float]:
        try:
            import torch
            import torchaudio
        except ImportError as exc:
            raise RuntimeError(
                "torch and torchaudio are required for production ECAPA embeddings"
            ) from exc

        waveform, sample_rate = torchaudio.load(io.BytesIO(audio.wav_bytes))
        if sample_rate != audio.sample_rate:
            raise RuntimeError("processed audio sample rate mismatch")

        classifier = self._load()
        with torch.no_grad():
            embedding = classifier.encode_batch(waveform)

        return embedding.squeeze().detach().cpu().tolist()
