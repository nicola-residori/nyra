from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class ModelTarget:
    provider: str
    model: str

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider is required")
        if not self.model.strip():
            raise ValueError("model is required")


@dataclass(frozen=True)
class LlmSettings:
    host: str
    port: int
    primary: ModelTarget
    fallback: ModelTarget | None
    api_keys: dict[str, str]

    @classmethod
    def load(cls) -> "LlmSettings":
        primary = ModelTarget(
            provider=os.getenv("NYRA_LLM_PRIMARY_PROVIDER", ""),
            model=os.getenv("NYRA_LLM_PRIMARY_MODEL", ""),
        )

        fallback_provider = os.getenv("NYRA_LLM_FALLBACK_PROVIDER")
        fallback_model = os.getenv("NYRA_LLM_FALLBACK_MODEL")
        if bool(fallback_provider) != bool(fallback_model):
            raise ValueError(
                "fallback provider and model must be configured together"
            )
        fallback = (
            ModelTarget(provider=fallback_provider, model=fallback_model)
            if fallback_provider and fallback_model
            else None
        )

        api_keys = {
            provider: value
            for provider, value in {
                "openai": os.getenv("NYRA_LLM_OPENAI_API_KEY"),
                "anthropic": os.getenv("NYRA_LLM_ANTHROPIC_API_KEY"),
            }.items()
            if value
        }

        return cls(
            host=os.getenv("NYRA_LLM_HOST", "0.0.0.0"),
            port=int(os.getenv("NYRA_LLM_PORT", "8090")),
            primary=primary,
            fallback=fallback,
            api_keys=api_keys,
        )
