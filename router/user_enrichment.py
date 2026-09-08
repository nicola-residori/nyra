from __future__ import annotations

from typing import Any


def _display_name(directory, user_id: Any) -> str | None:
    if not isinstance(user_id, str) or not user_id:
        return None
    try:
        reference = directory.get("home_assistant", user_id)
    except Exception:
        return None
    return reference.display_name if reference is not None else None


def enrich_profile(profile: dict, directory) -> dict:
    return {
        **profile,
        "user_display_name": _display_name(directory, profile.get("user_id")),
    }


def enrich_diagnostic(diagnostic: dict, directory) -> dict:
    return {
        **diagnostic,
        "identified_user_display_name": _display_name(
            directory, diagnostic.get("identified_user_id")
        ),
    }


def enrich_diagnostic_detail(detail: dict, directory) -> dict:
    candidates = [
        {
            **candidate,
            "user_display_name": _display_name(
                directory, candidate.get("user_id")
            ),
        }
        for candidate in detail.get("candidates", [])
    ]
    return {**detail, "candidates": candidates}


def enrich_wake_word_sample(sample: dict, directory) -> dict:
    return {
        **sample,
        "user_display_name": _display_name(directory, sample.get("user_id")),
    }
