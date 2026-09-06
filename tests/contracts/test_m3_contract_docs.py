from pathlib import Path

CONTRACT = Path(
    "docs/superpowers/specs/2026-08-31-component-contract-v1-design.md"
)


def contract_text() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def test_identified_diagnostic_detail_expires_after_15_minutes():
    text = contract_text()
    assert "IDENTIFIED       -> 15 minutes" in text
    assert "candidate scores expire with" in text


def test_uncertain_identity_continuity_uses_latest_certain_same_session_user():
    text = contract_text()
    assert "latest certainly identified user in SAME session" in text
    assert "Continuity never crosses sessions." in text


def test_runtime_identification_configuration_has_owner_and_snapshot_semantics():
    text = contract_text()
    assert "persistent Speaker ID runtime configuration" in text
    assert "persistent identification timeout" in text
    assert "configuration snapshot at operation start" in text


def test_wake_word_capture_session_is_exactly_one_attempt():
    text = contract_text()
    assert "represents exactly one capture attempt" in text
    assert "at most one permanent WakeWordSample" in text


def test_admin_manages_but_does_not_start_voice_collection():
    text = contract_text()
    assert "Admin does not start enrollment or wake-word capture." in text
    assert "Home Assistant starts both workflows" in text
