from types import SimpleNamespace

import pytest

from homeassistant.custom_components.nyra.enrollment import (
    EnrollmentConflict,
    EnrollmentUnauthorized,
)
from homeassistant.custom_components.nyra.panel import (
    ws_capture_wake_word,
    ws_record,
    ws_start,
    ws_state,
    ws_terminate,
)


class Connection:
    def __init__(self, user_id="user-nicola"):
        self.user = None if user_id is None else SimpleNamespace(id=user_id)
        self.results = []
        self.errors = []

    def send_result(self, message_id, result):
        self.results.append((message_id, result))

    def send_error(self, message_id, code, message):
        self.errors.append((message_id, code, message))


class Coordinator:
    def __init__(self):
        self.started = []
        self.recorded = []
        self.terminated = []
        self.restored = []

    async def async_restore(self, source_ids):
        self.restored.append(list(source_ids))
        return []

    def state_for_user(self, user_id):
        return [{"session_id": "enr_1", "profile_user_id": user_id}]

    async def async_start(self, **payload):
        self.started.append(payload)
        return {"session_id": "enr_1", **payload}

    async def async_record(self, user_id, session_id):
        self.recorded.append((user_id, session_id))
        return {"session_id": session_id, "capture_state": "RECORDING"}

    async def async_terminate(self, user_id, session_id, reason):
        self.terminated.append((user_id, session_id, reason))
        return {"session_id": session_id, "status": "TERMINATED"}


class WakeWordCoordinator:
    def __init__(self):
        self.captured = []

    async def async_capture(self, **payload):
        self.captured.append(payload)
        return {"session_id": "wwc_1", "status": "RECORDING", **payload}


@pytest.mark.asyncio
async def test_panel_commands_bind_every_operation_to_authenticated_user():
    coordinator = Coordinator()
    connection = Connection()

    await ws_state(None, connection, {"id": 1}, coordinator, ["nyra-mansarda"])
    await ws_start(None, connection, {
        "id": 2, "source_id": "nyra-mansarda", "language": "it-IT",
        "sample_count": 6,
    }, coordinator)
    await ws_record(None, connection, {
        "id": 3, "session_id": "enr_1",
    }, coordinator)
    await ws_terminate(None, connection, {
        "id": 4, "session_id": "enr_1",
    }, coordinator)

    assert connection.results[0] == (1, {
        "sources": ["nyra-mansarda"],
        "sessions": [{"session_id": "enr_1", "profile_user_id": "user-nicola"}],
    })
    assert coordinator.started == [{
        "authenticated_user_id": "user-nicola", "source_id": "nyra-mansarda",
        "language": "it-IT", "target_count": 6,
    }]
    assert coordinator.recorded == [("user-nicola", "enr_1")]
    assert coordinator.terminated == [("user-nicola", "enr_1", "user_cancelled")]


@pytest.mark.asyncio
async def test_state_discovers_sources_when_panel_is_opened_after_esphome_connects():
    connection = Connection()

    async def current_sources():
        return ["nyra-mansarda"]

    await ws_state(None, connection, {"id": 8}, Coordinator(), current_sources)

    assert connection.results[0][1]["sources"] == ["nyra-mansarda"]
    assert connection.results[0][1]["sessions"] == [
        {"session_id": "enr_1", "profile_user_id": "user-nicola"}
    ]


@pytest.mark.asyncio
async def test_panel_rejects_missing_authenticated_user_with_stable_error():
    connection = Connection(user_id=None)

    await ws_state(None, connection, {"id": 1}, Coordinator(), [])

    assert connection.results == []
    assert connection.errors == [(1, "unauthorized", "Autenticazione Home Assistant richiesta.")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,code",
    [
        (EnrollmentConflict("already recording"), "enrollment_conflict"),
        (EnrollmentUnauthorized("wrong owner"), "unauthorized"),
        (RuntimeError("offline"), "enrollment_failed"),
    ],
)
async def test_panel_maps_backend_errors_to_stable_codes(error, code):
    class Broken(Coordinator):
        async def async_record(self, user_id, session_id):
            raise error

    connection = Connection()

    await ws_record(None, connection, {"id": 7, "session_id": "enr_1"}, Broken())

    assert connection.results == []
    assert connection.errors[0][0:2] == (7, code)


def test_panel_frontend_contains_phrase_progress_and_one_record_control():
    from pathlib import Path

    frontend = Path(__file__).resolve().parents[2] / (
        "homeassistant/custom_components/nyra/frontend/nyra-enrollment-panel.js"
    )
    text = frontend.read_text(encoding="utf-8")

    assert "current_phrase" in text
    assert "accepted_count" in text
    assert "target_count" in text
    assert "Registra campione" in text
    assert 'type: "nyra/enrollment/record"' in text
    assert "wake word" in text.lower()
    assert "subscribeEvents" in text


@pytest.mark.asyncio
async def test_wake_word_capture_binds_authenticated_user_and_editable_text():
    coordinator = WakeWordCoordinator()
    connection = Connection()

    await ws_capture_wake_word(None, connection, {
        "id": 9,
        "source_id": "nyra-mansarda",
        "language": "it-IT",
        "wake_word_text": "Gina Casa",
    }, coordinator)

    assert coordinator.captured == [{
        "authenticated_user_id": "user-nicola",
        "source_id": "nyra-mansarda",
        "language": "it-IT",
        "wake_word_text": "Gina Casa",
    }]


def test_panel_is_nyra_configuration_with_two_distinct_sections():
    from pathlib import Path

    frontend = Path(__file__).resolve().parents[2] / (
        "homeassistant/custom_components/nyra/frontend/nyra-enrollment-panel.js"
    )
    text = frontend.read_text(encoding="utf-8")

    assert "Configurazione Nyra" in text
    assert "Profilo vocale" in text
    assert "Campioni wake word" in text
    assert 'type: "nyra/wake-word/capture"' in text
    assert "wake_word_text" in text
    assert "Campioni già salvati" in text
