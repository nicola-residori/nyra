from __future__ import annotations

import importlib
import sys


def ensure_shared_protocol() -> None:
    try:
        importlib.import_module("shared.protocol")
        return
    except ModuleNotFoundError as exc:
        if exc.name != "shared":
            raise

    from . import shared as bundled_shared

    sys.modules["shared"] = bundled_shared
    try:
        importlib.import_module("shared.protocol")
    except Exception:
        sys.modules.pop("shared", None)
        raise
