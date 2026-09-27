from __future__ import annotations
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class ModelTarget:
    provider:str
    model:str
    def __post_init__(self):
        if not self.provider.strip(): raise ValueError("provider is required")
        if not self.model.strip(): raise ValueError("model is required")

def _optional_target(prefix:str)->ModelTarget|None:
    provider=os.getenv(f"{prefix}_PROVIDER")
    model=os.getenv(f"{prefix}_MODEL")
    if bool(provider)!=bool(model):
        raise ValueError(f"{prefix} provider and model must be configured together")
    return ModelTarget(provider,model) if provider and model else None

@dataclass(frozen=True)
class LlmSettings:
    host:str
    port:int
    primary:ModelTarget
    fallback:ModelTarget|None
    api_keys:dict[str,str]
    semantic:ModelTarget
    reasoning:ModelTarget
    router_url:str|None=None
    @classmethod
    def load(cls):
        primary=ModelTarget(os.getenv("NYRA_LLM_PRIMARY_PROVIDER",""),os.getenv("NYRA_LLM_PRIMARY_MODEL",""))
        fallback=_optional_target("NYRA_LLM_FALLBACK")
        semantic=_optional_target("NYRA_LLM_SEMANTIC") or primary
        reasoning=_optional_target("NYRA_LLM_REASONING") or primary
        keys={k:v for k,v in {"openai":os.getenv("NYRA_LLM_OPENAI_API_KEY"),"anthropic":os.getenv("NYRA_LLM_ANTHROPIC_API_KEY")}.items() if v}
        return cls(os.getenv("NYRA_LLM_HOST","0.0.0.0"),int(os.getenv("NYRA_LLM_PORT","8090")),primary,fallback,keys,semantic,reasoning,os.getenv("NYRA_ROUTER_URL") or None)
