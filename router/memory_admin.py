from __future__ import annotations

from typing import Any


def owner_display_name(owner_user_id: str | None, user_directory) -> str | None:
    if owner_user_id is None:
        return None
    try:
        reference = user_directory.get("home_assistant", owner_user_id)
    except Exception:
        return None
    return reference.display_name if reference is not None else None


def enrich_memory_owners(value: Any, user_directory) -> Any:
    if isinstance(value, list):
        return [enrich_memory_owners(item, user_directory) for item in value]
    if not isinstance(value, dict):
        return value
    enriched = {
        key: enrich_memory_owners(item, user_directory)
        for key, item in value.items()
    }
    if "owner_user_id" in enriched:
        enriched["owner_display_name"] = owner_display_name(
            enriched.get("owner_user_id"), user_directory
        )
    return enriched

