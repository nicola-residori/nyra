from fastapi.testclient import TestClient
import tomllib

from memory.app import create_app
from memory.config import MemorySettings
from memory.embeddings import SentenceTransformerEmbeddingProvider


class LoadedEmbeddingProvider:
    provider_name = "test"
    model_name = "test-model"

    def prepare(self):
        return None


class FailingEmbeddingProvider:
    provider_name = "test"
    model_name = "broken-model"

    def prepare(self):
        raise RuntimeError("model cannot load")


def test_health_reports_liveness_without_initializing_dependencies(tmp_path):
    app = create_app(
        MemorySettings(data_root=tmp_path),
        embedding_provider=FailingEmbeddingProvider(),
    )

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json()["service"] == "nyra-memory"
    assert response.json()["status"] == "healthy"
    assert response.json()["uptime"] >= 0


def test_ready_requires_initialized_store_and_loaded_embedder(tmp_path):
    app = create_app(
        MemorySettings(data_root=tmp_path),
        embedding_provider=LoadedEmbeddingProvider(),
    )

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "ready": True,
        "storage": "initialized",
        "embedding": "loaded",
        "embedding_model": "test-model",
    }
    assert (tmp_path / "memory.sqlite3").exists()


def test_ready_reports_embedding_failure_without_hiding_storage_state(tmp_path):
    app = create_app(
        MemorySettings(data_root=tmp_path),
        embedding_provider=FailingEmbeddingProvider(),
    )

    with TestClient(app) as client:
        response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "ready": False,
        "storage": "initialized",
        "embedding": "unavailable",
        "embedding_model": "broken-model",
    }


def test_default_app_uses_the_configured_production_embedding_provider(tmp_path):
    app = create_app(MemorySettings(data_root=tmp_path, embedding_model="model-v2"))

    assert isinstance(
        app.state.embedding_provider, SentenceTransformerEmbeddingProvider
    )
    assert app.state.embedding_provider.model_name == "model-v2"


def test_memory_package_is_included_in_distribution_configuration():
    with open("pyproject.toml", "rb") as source:
        package_finder = tomllib.load(source)["tool"]["setuptools"]["packages"]["find"]
    assert "memory*" in package_finder["include"]
    assert "memory*" not in package_finder["exclude"]
