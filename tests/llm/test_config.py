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
def test_purpose_targets_override_primary(monkeypatch):
    monkeypatch.setenv("NYRA_LLM_PRIMARY_PROVIDER","openai")
    monkeypatch.setenv("NYRA_LLM_PRIMARY_MODEL","default")
    monkeypatch.setenv("NYRA_LLM_SEMANTIC_PROVIDER","openai")
    monkeypatch.setenv("NYRA_LLM_SEMANTIC_MODEL","semantic")
    monkeypatch.setenv("NYRA_LLM_REASONING_PROVIDER","openai")
    monkeypatch.setenv("NYRA_LLM_REASONING_MODEL","reasoning")
    s=LlmSettings.load()
    assert s.semantic.model=="semantic"
    assert s.reasoning.model=="reasoning"

def test_purpose_targets_default_to_primary(monkeypatch):
    monkeypatch.setenv("NYRA_LLM_PRIMARY_PROVIDER","openai")
    monkeypatch.setenv("NYRA_LLM_PRIMARY_MODEL","default")
    for n in ("NYRA_LLM_SEMANTIC_PROVIDER","NYRA_LLM_SEMANTIC_MODEL","NYRA_LLM_REASONING_PROVIDER","NYRA_LLM_REASONING_MODEL"):
        monkeypatch.delenv(n,raising=False)
    s=LlmSettings.load()
    assert s.semantic==s.primary and s.reasoning==s.primary

@pytest.mark.parametrize("prefix",["SEMANTIC","REASONING"])
def test_purpose_target_requires_provider_and_model(monkeypatch,prefix):
    monkeypatch.setenv("NYRA_LLM_PRIMARY_PROVIDER","openai")
    monkeypatch.setenv("NYRA_LLM_PRIMARY_MODEL","default")
    monkeypatch.setenv(f"NYRA_LLM_{prefix}_PROVIDER","openai")
    monkeypatch.delenv(f"NYRA_LLM_{prefix}_MODEL",raising=False)
    with pytest.raises(ValueError): LlmSettings.load()
