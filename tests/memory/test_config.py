from pathlib import Path

from memory.config import MemorySettings


def test_settings_load_memory_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("NYRA_MEMORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("NYRA_MEMORY_HOST", "127.0.0.1")
    monkeypatch.setenv("NYRA_MEMORY_PORT", "8190")
    monkeypatch.setenv("NYRA_MEMORY_MODEL", "test-model")
    monkeypatch.setenv("NYRA_MEMORY_SEARCH_LIMIT", "7")
    monkeypatch.setenv("NYRA_MEMORY_SIMILARITY_FLOOR", "0.42")
    monkeypatch.setenv("NYRA_MEMORY_REQUEST_TIMEOUT_SECONDS", "1.25")
    monkeypatch.setenv("NYRA_ROUTER_URL", "http://router.test:8090")

    settings = MemorySettings.load()

    assert settings.data_root == tmp_path
    assert settings.database_path == tmp_path / "memory.sqlite3"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8190
    assert settings.embedding_model == "test-model"
    assert settings.search_limit == 7
    assert settings.similarity_floor == 0.42
    assert settings.request_timeout_seconds == 1.25
    assert settings.router_url == "http://router.test:8090"


def test_settings_have_deployable_local_defaults(monkeypatch):
    for name in (
        "NYRA_MEMORY_DATA_ROOT",
        "NYRA_MEMORY_HOST",
        "NYRA_MEMORY_PORT",
        "NYRA_MEMORY_MODEL",
        "NYRA_MEMORY_SEARCH_LIMIT",
        "NYRA_MEMORY_SIMILARITY_FLOOR",
        "NYRA_MEMORY_REQUEST_TIMEOUT_SECONDS",
        "NYRA_ROUTER_URL",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = MemorySettings.load()

    assert settings.data_root == Path("/var/lib/nyra-memory")
    assert settings.port == 8090
    assert settings.embedding_model == (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
    assert settings.search_limit == 10
    assert settings.similarity_floor == 0.35
    assert settings.request_timeout_seconds == 3.0

