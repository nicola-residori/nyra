from __future__ import annotations
from copy import deepcopy
from typing import Any

DEFAULT_SENSITIVE = {"authorization", "token", "api_key", "password", "secret", "cookie"}
REDACTED = "***REDACTED***"

def redact(value: Any, sensitive_keys: set[str] | None = None) -> Any:
    keys = {k.lower() for k in (sensitive_keys or DEFAULT_SENSITIVE)}
    def walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: (REDACTED if str(k).lower() in keys else walk(v)) for k, v in obj.items()}
        if isinstance(obj, list): return [walk(v) for v in obj]
        if isinstance(obj, tuple): return [walk(v) for v in obj]
        return deepcopy(obj)
    return walk(value)
