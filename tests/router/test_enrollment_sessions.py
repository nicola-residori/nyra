from pathlib import Path

import pytest

from router.enrollment import (
    EnrollmentConflict,
    EnrollmentService,
    EnrollmentSessionStore,
    EnrollmentStatus,
    PhraseLength,
)


def service(tmp_path: Path, generator=None) -> EnrollmentService:
    store = EnrollmentSessionStore(tmp_path / "router.db")
    store.initialize()
    return EnrollmentService(store, phrase_generator=generator)


def test_default_six_phrase_plan_is_localized_and_balanced(tmp_path: Path):
    enrollment = service(tmp_path)

    session = enrollment.start("user-nicola", "nyra-mansarda", "it-IT", 6)

    assert session.profile_user_id == "user-nicola"
    assert session.source_id == "nyra-mansarda"
    assert [phrase.length_class for phrase in session.phrases] == [
        PhraseLength.SHORT,
        PhraseLength.MEDIUM,
        PhraseLength.LONG,
        PhraseLength.SHORT,
        PhraseLength.MEDIUM,
        PhraseLength.LONG,
    ]
    assert all(phrase.language == "it-IT" and phrase.text for phrase in session.phrases)
    assert session.current_phrase == session.phrases[0]


def test_rejected_attempt_repeats_phrase_and_accepted_samples_complete_once(tmp_path: Path):
    enrollment = service(tmp_path)
    started = enrollment.start("user-nicola", "nyra-mansarda", "it-IT", 6)

    rejected = enrollment.record_attempt(started.session_id, "REJECTED", reason_code="TOO_SHORT")
    assert rejected.accepted_count == 0
    assert rejected.current_phrase == started.current_phrase

    for index in range(6):
        current = enrollment.record_attempt(started.session_id, "ACCEPTED", sample_id=f"sample-{index}")

    assert current.status is EnrollmentStatus.COMPLETED
    assert current.accepted_count == 6
    assert current.accepted_sample_ids == tuple(f"sample-{index}" for index in range(6))
    assert current.current_phrase is None
    with pytest.raises(EnrollmentConflict):
        enrollment.record_attempt(started.session_id, "ACCEPTED", sample_id="late")
    assert enrollment.terminate(started.session_id, "user_cancelled") == current


def test_termination_preserves_four_accepted_samples_and_is_exactly_once(tmp_path: Path):
    enrollment = service(tmp_path)
    started = enrollment.start("user-nicola", "nyra-mansarda", "en-US", 6)
    for index in range(4):
        enrollment.record_attempt(started.session_id, "ACCEPTED", sample_id=f"sample-{index}")

    terminated = enrollment.terminate(started.session_id, "user_cancelled")

    assert terminated.status is EnrollmentStatus.TERMINATED
    assert terminated.termination_reason == "user_cancelled"
    assert terminated.accepted_count == 4
    assert terminated.accepted_sample_ids == ("sample-0", "sample-1", "sample-2", "sample-3")
    assert enrollment.terminate(started.session_id, "user_cancelled") == terminated
    with pytest.raises(EnrollmentConflict):
        enrollment.terminate(started.session_id, "different_reason")


def test_invalid_generated_plan_uses_localized_deterministic_fallback(tmp_path: Path):
    class BrokenGenerator:
        def generate(self, language, target_count):
            raise RuntimeError("offline")

    enrollment = service(tmp_path, BrokenGenerator())
    italian = enrollment.start("u1", "s1", "it-IT", 3)
    english = enrollment.start("u2", "s2", "en-US", 3)

    assert italian.phrases[0].text != english.phrases[0].text
    assert [p.language for p in italian.phrases] == ["it-IT"] * 3
    assert [p.language for p in english.phrases] == ["en-US"] * 3


def test_store_restores_active_session_after_restart(tmp_path: Path):
    database = tmp_path / "router.db"
    first = EnrollmentSessionStore(database)
    first.initialize()
    session = EnrollmentService(first).start("u", "s", "en-US", 3)
    EnrollmentService(first).record_attempt(session.session_id, "ACCEPTED", sample_id="one")

    second = EnrollmentSessionStore(database)
    second.initialize()
    restored = EnrollmentService(second).get(session.session_id)

    assert restored.accepted_sample_ids == ("one",)
    assert restored.current_phrase == restored.phrases[1]


def test_start_is_idempotent_for_same_user_and_source(tmp_path: Path):
    enrollment = service(tmp_path)

    first = enrollment.start("user-nicola", "nyra-mansarda", "it-IT", 6)
    second = enrollment.start("user-nicola", "nyra-mansarda", "it-IT", 6)

    assert second.session_id == first.session_id
    assert second.accepted_sample_ids == ()
    assert enrollment.store.get_active_for_source("nyra-mansarda") == first


def test_start_rejects_active_source_owned_by_another_user(tmp_path: Path):
    enrollment = service(tmp_path)
    enrollment.start("user-nicola", "nyra-mansarda", "it-IT", 6)

    with pytest.raises(EnrollmentConflict, match="ACTIVE_ENROLLMENT_CONFLICT"):
        enrollment.start("user-alice", "nyra-mansarda", "it-IT", 6)
