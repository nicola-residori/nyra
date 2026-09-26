import pytest

from llm.config import LlmSettings


def test_settings_load_primary_and_fallback_from_environment(monkeypatch):
    monkeypatch.setenv("NYRA_LLM_HOST", "127.0.0.1")
    monkeypatch.setenv("NYRA_LLM_PORT", "8094")
    monkeypatch.setenv("NYRA_LLM_PRIMARY_PROVIDER", "openai")
    monkeypatch.setenv("NYRA_LLM_PRIMARY_MODEL", "gpt-primary")
    monkeypatch.setenv("NYRA_LLM_FALLBACK_PROVIDER", "anthropic")
    monkeypatch.setenv("NYRA_LLM_FALLBACK_MODEL", "claude-fallback")
    monkeypatch.setenv("NYRA_LLM_OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("NYRA_LLM_ANTHROPIC_API_KEY", "anthropic-secret")

    settings = LlmSettings.load()

    assert settings.host == "127.0.0.1"
    assert settings.port == 8094
    assert settings.primary.provider == "openai"
    assert settings.primary.model == "gpt-primary"
    assert settings.fallback.provider == "anthropic"
    assert settings.fallback.model == "claude-fallback"
    assert settings.api_keys == {
        "openai": "openai-secret",
        "anthropic": "anthropic-secret",
    }


def test_fallback_is_optional(monkeypatch):
    monkeypatch.setenv("NYRA_LLM_PRIMARY_PROVIDER", "openai")
    monkeypatch.setenv("NYRA_LLM_PRIMARY_MODEL", "gpt-primary")
    monkeypatch.delenv("NYRA_LLM_FALLBACK_PROVIDER", raising=False)
    monkeypatch.delenv("NYRA_LLM_FALLBACK_MODEL", raising=False)

    settings = LlmSettings.load()

    assert settings.fallback is None


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("", "gpt-primary"),
        ("openai", ""),
    ],
)
def test_primary_provider_and_model_are_required(monkeypatch, provider, model):
    monkeypatch.setenv("NYRA_LLM_PRIMARY_PROVIDER", provider)
    monkeypatch.setenv("NYRA_LLM_PRIMARY_MODEL", model)

    with pytest.raises(ValueError):
        LlmSettings.load()


def test_fallback_provider_and_model_must_be_configured_together(monkeypatch):
    monkeypatch.setenv("NYRA_LLM_PRIMARY_PROVIDER", "openai")
    monkeypatch.setenv("NYRA_LLM_PRIMARY_MODEL", "gpt-primary")
    monkeypatch.setenv("NYRA_LLM_FALLBACK_PROVIDER", "anthropic")
    monkeypatch.delenv("NYRA_LLM_FALLBACK_MODEL", raising=False)

    with pytest.raises(ValueError):
        LlmSettings.load()


def test_api_keys_are_not_required_for_provider_independent_config(monkeypatch):
    monkeypatch.setenv("NYRA_LLM_PRIMARY_PROVIDER", "local")
    monkeypatch.setenv("NYRA_LLM_PRIMARY_MODEL", "local-model")
    monkeypatch.delenv("NYRA_LLM_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("NYRA_LLM_ANTHROPIC_API_KEY", raising=False)

    settings = LlmSettings.load()

    assert settings.api_keys == {}
