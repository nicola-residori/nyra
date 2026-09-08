from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Protocol


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


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str

    def embed(self, text: str) -> EmbeddingVector: ...

