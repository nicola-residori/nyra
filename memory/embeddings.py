from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from threading import Lock
from typing import Protocol


class EmbeddingUnavailable(RuntimeError):
    pass


class EmbeddingModelMismatch(RuntimeError):
    pass


@dataclass(frozen=True)
class EmbeddingVector:
    values: tuple[float, ...]
    provider: str
    model: str

    def __post_init__(self):
        if not self.values:
            raise ValueError("embedding vector must not be empty")
        if not all(isfinite(value) for value in self.values):
            raise ValueError("embedding vector values must be finite")
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("embedding provider and model are required")

    def normalized(self) -> "EmbeddingVector":
        magnitude = sqrt(sum(value * value for value in self.values))
        if magnitude == 0:
            raise ValueError("zero-length embedding cannot be normalized")
        return EmbeddingVector(
            values=tuple(value / magnitude for value in self.values),
            provider=self.provider.strip(),
            model=self.model.strip(),
        )


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    def embed(self, text: str) -> EmbeddingVector: ...


class SentenceTransformerEmbeddingProvider:
    provider_name = "sentence-transformers"

    def __init__(self, model_name: str, *, model_factory=None):
        self.model_name = model_name
        self._model_factory = model_factory
        self._model = None
        self._lock = Lock()

    def prepare(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            factory = self._model_factory
            if factory is None:
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise EmbeddingUnavailable(
                        "sentence-transformers is not installed"
                    ) from exc
                factory = SentenceTransformer
            self._model = factory(self.model_name)

    def embed(self, text: str) -> EmbeddingVector:
        if self._model is None:
            raise EmbeddingUnavailable("embedding provider is not prepared")
        encoded = self._model.encode(
            [text], normalize_embeddings=True, convert_to_numpy=True
        )[0]
        values = encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)
        return EmbeddingVector(
            values=tuple(float(value) for value in values),
            provider=self.provider_name,
            model=self.model_name,
        ).normalized()
