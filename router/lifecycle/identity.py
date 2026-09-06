from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from router.speaker_identity import SpeakerIdentityOutcome, SpeakerIdentityResult
from shared.protocol.context import IdentityResolutionSource


class IdentityOutcome(StrEnum):
    IDENTIFIED = "IDENTITY_IDENTIFIED"
    CONFIRMED = "IDENTITY_CONFIRMED"
    CHANGED = "IDENTITY_CHANGED"
    CONTINUITY = "IDENTITY_CONTINUITY"
    GUEST = "IDENTITY_GUEST"


@dataclass(frozen=True)
class IdentityResolution:
    current_user_id: str
    outcome: IdentityOutcome
    previous_user_id: str | None = None
    last_trusted_user_id: str | None = None
    resolution_source: IdentityResolutionSource = IdentityResolutionSource.GUEST_FALLBACK
    timed_out: bool = False


def resolve_speaker_identity(last_trusted_user_id: str | None, result: SpeakerIdentityResult | None, *, timed_out: bool = False) -> IdentityResolution:
    if result is not None and result.outcome is SpeakerIdentityOutcome.IDENTIFIED:
        detected = result.identified_user_id
        if detected is None:
            raise ValueError("IDENTIFIED result requires identified_user_id")
        if last_trusted_user_id is None:
            outcome = IdentityOutcome.IDENTIFIED
        elif last_trusted_user_id == detected:
            outcome = IdentityOutcome.CONFIRMED
        else:
            outcome = IdentityOutcome.CHANGED
        return IdentityResolution(
            detected, outcome, last_trusted_user_id, detected,
            IdentityResolutionSource.SPEAKER_IDENTIFICATION, False
        )

    if last_trusted_user_id is not None:
        return IdentityResolution(
            last_trusted_user_id, IdentityOutcome.CONTINUITY,
            last_trusted_user_id, last_trusted_user_id,
            IdentityResolutionSource.SESSION_CONTINUITY, timed_out
        )

    return IdentityResolution(
        "guest", IdentityOutcome.GUEST, None, None,
        IdentityResolutionSource.GUEST_FALLBACK, timed_out
    )


def resolve_identity_outcome(previous_user_id: str | None, detected_user_id: str | None) -> IdentityResolution:
    if detected_user_id is None:
        return IdentityResolution("guest", IdentityOutcome.GUEST, previous_user_id)
    if previous_user_id is None:
        return IdentityResolution(detected_user_id, IdentityOutcome.IDENTIFIED, None)
    if previous_user_id == detected_user_id:
        return IdentityResolution(detected_user_id, IdentityOutcome.CONFIRMED, previous_user_id)
    return IdentityResolution(detected_user_id, IdentityOutcome.CHANGED, previous_user_id)
