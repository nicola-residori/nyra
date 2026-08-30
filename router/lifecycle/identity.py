from __future__ import annotations
from dataclasses import dataclass
from enum import StrEnum


class IdentityOutcome(StrEnum):
    IDENTIFIED = "IDENTITY_IDENTIFIED"
    CONFIRMED = "IDENTITY_CONFIRMED"
    CHANGED = "IDENTITY_CHANGED"
    GUEST = "IDENTITY_GUEST"


@dataclass(frozen=True)
class IdentityResolution:
    current_user_id: str
    outcome: IdentityOutcome
    previous_user_id: str | None = None


def resolve_identity_outcome(previous_user_id: str | None, detected_user_id: str | None) -> IdentityResolution:
    if detected_user_id is None:
        return IdentityResolution("guest", IdentityOutcome.GUEST, previous_user_id)
    if previous_user_id is None:
        return IdentityResolution(detected_user_id, IdentityOutcome.IDENTIFIED, None)
    if previous_user_id == detected_user_id:
        return IdentityResolution(detected_user_id, IdentityOutcome.CONFIRMED, previous_user_id)
    return IdentityResolution(detected_user_id, IdentityOutcome.CHANGED, previous_user_id)
