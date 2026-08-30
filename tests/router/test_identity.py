from router.lifecycle.identity import IdentityOutcome, resolve_identity_outcome


def test_identity_outcomes():
    first = resolve_identity_outcome(None, "user-a")
    assert first.outcome is IdentityOutcome.IDENTIFIED and first.current_user_id == "user-a"
    same = resolve_identity_outcome("user-a", "user-a")
    assert same.outcome is IdentityOutcome.CONFIRMED
    changed = resolve_identity_outcome("user-a", "user-b")
    assert changed.outcome is IdentityOutcome.CHANGED and changed.previous_user_id == "user-a"
    guest = resolve_identity_outcome("user-a", None)
    assert guest.outcome is IdentityOutcome.GUEST and guest.current_user_id == "guest"
