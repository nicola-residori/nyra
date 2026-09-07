from __future__ import annotations

import io
import sys
import wave
from array import array
from types import SimpleNamespace
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

    def load(self):
        """Load and cache the production model, raising when unavailable."""
        return self._load()

    def validate(self) -> None:
        """Load the model and execute one local inference for readiness."""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\x00\x00" * 16000)
        vector = self.embed(
            SimpleNamespace(wav_bytes=buffer.getvalue(), sample_rate=16000)
        )
        if not vector:
            raise RuntimeError("ECAPA readiness inference returned no embedding")

    def embed(self, audio: "ProcessedAudio") -> list[float]:
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError("torch is required for production ECAPA embeddings") from exc

        try:
            with wave.open(io.BytesIO(audio.wav_bytes), "rb") as wav:
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                sample_rate = wav.getframerate()
                frames = wav.readframes(wav.getnframes())
        except (wave.Error, EOFError) as exc:
            raise RuntimeError("processed audio is not a valid WAV") from exc
        if channels != 1 or sample_width != 2:
            raise RuntimeError("processed audio must be mono PCM16")
        if sample_rate != audio.sample_rate:
            raise RuntimeError("processed audio sample rate mismatch")

        samples = array("h")
        samples.frombytes(frames)
        if sys.byteorder != "little":
            samples.byteswap()
        waveform = torch.tensor(samples, dtype=torch.float32).unsqueeze(0) / 32768.0

        classifier = self._load()
        with torch.no_grad():
            embedding = classifier.encode_batch(waveform)

        return embedding.squeeze().detach().cpu().tolist()
