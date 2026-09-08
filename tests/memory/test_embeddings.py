import math

import pytest

from memory.embeddings import (
    EmbeddingUnavailable,
    EmbeddingVector,
    SentenceTransformerEmbeddingProvider,
)


def test_embedding_vector_normalizes_to_unit_length():
    normalized = EmbeddingVector(
        values=(3.0, 4.0), provider="fake", model="v1"
    ).normalized()

    assert normalized.values == pytest.approx((0.6, 0.8))
    assert math.sqrt(sum(value * value for value in normalized.values)) == pytest.approx(1.0)


def test_zero_embedding_vector_cannot_be_normalized():
    with pytest.raises(ValueError, match="zero-length embedding"):
        EmbeddingVector(
            values=(0.0, 0.0), provider="fake", model="v1"
        ).normalized()


class FakeModel:
    def __init__(self):
        self.calls = []

    def encode(self, texts, **options):
        self.calls.append((texts, options))
        return [[3.0, 4.0]]


def test_sentence_transformer_provider_loads_once_and_returns_normalized_vector():
    model = FakeModel()
    loads = []
    provider = SentenceTransformerEmbeddingProvider(
        "multilingual-test",
        model_factory=lambda name: loads.append(name) or model,
    )

    provider.prepare()
    provider.prepare()
    vector = provider.embed("espresso")

    assert loads == ["multilingual-test"]
    assert vector.values == pytest.approx((0.6, 0.8))
    assert model.calls == [
        (["espresso"], {"normalize_embeddings": True, "convert_to_numpy": True})
    ]


def test_sentence_transformer_provider_rejects_inference_before_prepare():
    provider = SentenceTransformerEmbeddingProvider(
        "multilingual-test", model_factory=lambda _: FakeModel()
    )

    with pytest.raises(EmbeddingUnavailable, match="not prepared"):
        provider.embed("espresso")

