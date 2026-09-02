#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "shared"
TARGET = ROOT / "homeassistant" / "custom_components" / "nyra" / "shared"


def main() -> None:
    if not (SOURCE / "protocol").is_dir():
        raise SystemExit(f"Canonical protocol directory not found: {SOURCE / 'protocol'}")

    if TARGET.exists():
        shutil.rmtree(TARGET)

    TARGET.mkdir(parents=True)
    shutil.copy2(SOURCE / "__init__.py", TARGET / "__init__.py")
    shutil.copytree(SOURCE / "protocol", TARGET / "protocol")

    for cache in TARGET.rglob("__pycache__"):
        shutil.rmtree(cache)


if __name__ == "__main__":
    main()
