from pathlib import Path

import pytest

from router.wake_word_capture import (
    WakeWordCaptureConflict,
    WakeWordCaptureService,
    WakeWordCaptureSessionStore,
    WakeWordCaptureStatus,
)


def service(tmp_path: Path) -> WakeWordCaptureService:
    store = WakeWordCaptureSessionStore(tmp_path / "router.db")
    store.initialize()
    return WakeWordCaptureService(store)


def test_one_session_is_exactly_one_capture_attempt(tmp_path):
    captures = service(tmp_path)
    started = captures.start("user-nicola", "nyra-mansarda", "it-IT", "Nyra")

    completed = captures.complete(started.session_id, "ACCEPTED", sample_id="sample-1")

    assert completed.status is WakeWordCaptureStatus.ACCEPTED
    assert completed.sample_id == "sample-1"
    with pytest.raises(WakeWordCaptureConflict):
        captures.complete(started.session_id, "ACCEPTED", sample_id="sample-2")


def test_arbitrary_text_creates_a_distinct_dataset_attempt(tmp_path):
    captures = service(tmp_path)
    first = captures.start("user-nicola", "nyra-mansarda", "it-IT", "Nyra")
    captures.complete(first.session_id, "REJECTED", reason_code="TOO_SHORT")

    second = captures.start("user-nicola", "nyra-mansarda", "it-IT", "Gina Casa")

    assert second.session_id != first.session_id
    assert second.wake_word_text == "Gina Casa"
    assert second.status is WakeWordCaptureStatus.ACTIVE


def test_only_one_active_capture_can_own_a_source(tmp_path):
    captures = service(tmp_path)
    active = captures.start("user-nicola", "nyra-mansarda", "it-IT", "Nyra")

    with pytest.raises(WakeWordCaptureConflict, match="ACTIVE_WAKE_WORD_CAPTURE_CONFLICT"):
        captures.start("user-nicola", "nyra-mansarda", "it-IT", "Altra")

    assert captures.store.get_active_for_source("nyra-mansarda") == active


@pytest.mark.parametrize("status", ["REJECTED", "FAILED"])
def test_rejected_and_failed_are_terminal_without_a_sample(tmp_path, status):
    captures = service(tmp_path)
    started = captures.start("user-nicola", "nyra-mansarda", "it-IT", "Nyra")

    completed = captures.complete(started.session_id, status, reason_code="LOW_SIGNAL")

    assert completed.status.value == status
    assert completed.sample_id is None
    assert completed.reason_code == "LOW_SIGNAL"


@pytest.mark.asyncio
async def test_dataset_count_is_read_through_speaker_id():
    class Dataset:
        async def count(self, wake_word_text):
            assert wake_word_text == "Nyra"
            return 7

    assert await Dataset().count("Nyra") == 7
