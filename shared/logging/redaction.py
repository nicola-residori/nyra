from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_SENSITIVE = {
    "authorization", "token", "api_key", "password", "secret", "cookie"
}
REDACTED = "***REDACTED***"


def redact(value: Any, sensitive_keys: set[str] | None = None) -> Any:
    keys = {key.lower() for key in (sensitive_keys or DEFAULT_SENSITIVE)}

    def walk(item: Any) -> Any:
        if isinstance(item, dict):
            return {
                key: REDACTED if str(key).lower() in keys else walk(child)
                for key, child in item.items()
            }
        if isinstance(item, list):
            return [walk(child) for child in item]
        if isinstance(item, tuple):
            return [walk(child) for child in item]
        return deepcopy(item)

    return walk(value)

