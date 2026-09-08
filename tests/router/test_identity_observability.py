from __future__ import annotations

import json
import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from router.app import create_app
from router.audio_streaming import CorrelatedIdentityAudioSink
from router.config import RouterSettings
from router.enrollment import EnrollmentService, EnrollmentSessionStore
from router.lifecycle.service import (
    ContextResult,
    LifecycleDecision,
    RequestLifecycleService,
    SkillMatch,
)
from router.lifecycle.store import RequestStateStore
from router.observability.service import ObservabilityService
from router.speaker_identity import SpeakerIdentityOutcome, SpeakerIdentityResult
from router.storage.sqlite import SQLiteObservabilityStore
from router.wake_word_capture import WakeWordCaptureService, WakeWordCaptureSessionStore
from shared.audio_streaming import AudioStreamPurpose, AudioStreamStart
from shared.protocol.ids import new_request_id, new_session_id, new_span_id, new_trace_id
from shared.protocol.observability import LogKind, LogLevel, LogRecord
from shared.protocol.requests import NyraRequest


class Broker:
    async def publish_state(self, event):
        pass

    async def publish_identity_feedback(self, event):
        pass

    async def publish_session_closed(self, event):
        pass


class ContextPort:
    async def resolve(self, request, identity_user_id):
        return ContextResult(data={}, semantic_memory_required=False)


class MemoryPort:
    async def search(self, request, identity_user_id, context):
        return {}


class SkillPort:
    async def check(self, request, context, memory, pending_state):
        return SkillMatch(matched=True, token="local")

    async def execute(self, match, request, context, memory, pending_state):
        return LifecycleDecision.completed("ok")


class LlmPort:
    async def reason(self, request, context, memory, pending_state):
        return LifecycleDecision.completed("ok")


class SequenceIdentity:
    def __init__(self, results):
        self.results = list(results)

    async def identify(self, request, trace_id):
        return self.results.pop(0)


def identified(user_id="nicola"):
    return SpeakerIdentityResult(
        SpeakerIdentityOutcome.IDENTIFIED, user_id, 0.82, "diag-ok", None
    )


def not_recognized():
    return SpeakerIdentityResult(
        SpeakerIdentityOutcome.NOT_RECOGNIZED,
        None,
        0.31,
        "diag-low",
        "BELOW_THRESHOLD",
    )


def request(session_id, request_id):
    return NyraRequest.model_validate(
        {
            "type": "ha_speaker",
            "session_id": session_id,
            "request_id": request_id,
            "language": "it-IT",
            "source": {"id": "nyra-mansarda", "area": "mansarda"},
            "input": {"text": "che ore sono"},
        }
    )


def service(tmp_path, identity):
    database = tmp_path / "router.db"
    request_store = RequestStateStore(database)
    request_store.initialize()
    log_store = SQLiteObservabilityStore(database)
    log_store.initialize()
    observability = ObservabilityService(log_store, request_store=request_store)
    lifecycle = RequestLifecycleService(
        store=request_store,
        broker=Broker(),
        identity_port=identity,
        context_port=ContextPort(),
        memory_port=MemoryPort(),
        skill_port=SkillPort(),
        llm_port=LlmPort(),
        clock=lambda: datetime.now(timezone.utc),
        observability=observability,
        identification_timeout_seconds=1.0,
    )
    return lifecycle, log_store


@pytest.mark.asyncio
async def test_identity_timeline_separates_biometric_completion_from_continuity(tmp_path):
    lifecycle, logs = service(tmp_path, SequenceIdentity([identified(), not_recognized()]))
    session_id = new_session_id()
    await lifecycle.execute(request(session_id, new_request_id()))

    second_request_id = new_request_id()
    await lifecycle.execute(request(session_id, second_request_id))
    rows = sorted(
        logs.query_logs({"request_id": second_request_id, "limit": 100}),
        key=lambda row: row["id"],
    )
    identity_rows = [row for row in rows if row["event"].startswith("identity.")]

    assert [row["event"] for row in identity_rows] == [
        "identity.started",
        "identity.completed",
        "identity.resolved",
    ]
    assert identity_rows[1]["params"] == {
        "source_id": "nyra-mansarda",
        "outcome": "NOT_RECOGNIZED",
        "identified_user_id": None,
        "best_score": 0.31,
        "diagnostic_id": "diag-low",
        "reason_code": "BELOW_THRESHOLD",
        "latency_ms": pytest.approx(identity_rows[1]["params"]["latency_ms"]),
        "late_result": False,
    }
    assert identity_rows[1]["params"]["latency_ms"] >= 0
    assert identity_rows[2]["params"]["user_id"] == "nicola"
    assert identity_rows[2]["params"]["resolution"] == "SESSION_CONTINUITY"
    assert identity_rows[2]["params"]["biometric_outcome"] == "NOT_RECOGNIZED"


@pytest.mark.asyncio
async def test_identity_general_observability_excludes_biometric_payloads(tmp_path):
    lifecycle, logs = service(tmp_path, SequenceIdentity([identified()]))
    request_id = new_request_id()
    await lifecycle.execute(request(new_session_id(), request_id))

    serialized = json.dumps(logs.query_logs({"request_id": request_id, "limit": 100}))
    assert "candidate_scores" not in serialized
    assert "embedding" not in serialized
    assert "audio_bytes" not in serialized


def _identity_log(event, *, result=None, source="speaker-a", latency=None, **params):
    values = {"source_id": source, **params}
    if latency is not None:
        values["latency_ms"] = latency
    return LogRecord(
        ct="ROUTER",
        level=LogLevel.INFO,
        kind=LogKind.EVENT,
        event=event,
        trace_id=new_trace_id(),
        span_id=new_span_id("ROUTER", "identity"),
        operation="speaker_identity",
        result=result,
        params=values,
    )


def test_identity_metrics_include_rates_sources_latency_timeouts_and_late_results(tmp_path):
    store = SQLiteObservabilityStore(tmp_path / "router.db")
    store.initialize()
    records = []
    for source, outcome, latency in (
        ("speaker-a", "IDENTIFIED", 10.0),
        ("speaker-a", "NOT_RECOGNIZED", 20.0),
        ("speaker-b", "FAILED", 30.0),
        ("speaker-b", "IDENTIFIED", 40.0),
    ):
        records.append(_identity_log("identity.started", source=source))
        records.append(
            _identity_log(
                "identity.completed",
                source=source,
                result=outcome,
                outcome=outcome,
                latency=latency,
                late_result=outcome == "FAILED",
            )
        )
        records.append(
            _identity_log(
                "identity.resolved",
                source=source,
                timed_out=outcome == "FAILED",
            )
        )
    store.insert_logs(records)

    metrics = store.identity_metrics()

    assert metrics["attempts"] == 4
    assert metrics["outcome_counts"] == {
        "IDENTIFIED": 2,
        "NOT_RECOGNIZED": 1,
        "FAILED": 1,
    }
    assert metrics["outcome_rates"]["IDENTIFIED"] == pytest.approx(0.5)
    assert metrics["by_source"]["speaker-a"]["attempts"] == 2
    assert metrics["by_source"]["speaker-b"]["outcome_counts"]["FAILED"] == 1
    assert metrics["latency_ms"] == {
        "average": pytest.approx(25.0),
        "p50": pytest.approx(25.0),
        "p95": pytest.approx(38.5),
        "p99": pytest.approx(39.7),
    }
    assert metrics["timeout_count"] == 1
    assert metrics["timeout_rate"] == pytest.approx(0.25)
    assert metrics["late_result_count"] == 1
    assert metrics["late_result_rate"] == pytest.approx(0.25)


def test_identity_metrics_are_available_through_router_api(tmp_path):
    app = create_app(
        RouterSettings(database_path=tmp_path / "router.db"), audio_sink=object()
    )
    with TestClient(app) as client:
        app.state.store.insert_logs(
            [
                _identity_log("identity.started"),
                _identity_log(
                    "identity.completed",
                    result="IDENTIFIED",
                    outcome="IDENTIFIED",
                    latency=12.0,
                    late_result=False,
                ),
                _identity_log("identity.resolved", timed_out=False),
            ]
        )
        response = client.get("/v1/metrics/identity")

    assert response.status_code == 200
    assert response.json()["attempts"] == 1
    assert response.json()["outcome_counts"]["IDENTIFIED"] == 1


@pytest.mark.asyncio
async def test_timed_out_identity_is_resolved_before_late_completion_is_recorded(tmp_path):
    class SlowIdentity:
        async def identify(self, request, trace_id):
            await asyncio.sleep(0.03)
            return identified()

    lifecycle, logs = service(tmp_path, SlowIdentity())
    lifecycle.identification_timeout_seconds = 0.005
    request_id = new_request_id()
    await lifecycle.execute(request(new_session_id(), request_id))
    await asyncio.sleep(0.05)

    rows = sorted(
        logs.query_logs({"request_id": request_id, "limit": 100}),
        key=lambda row: row["id"],
    )
    identity_rows = [row for row in rows if row["event"].startswith("identity.")]
    assert [row["event"] for row in identity_rows] == [
        "identity.started",
        "identity.resolved",
        "identity.completed",
    ]
    assert identity_rows[1]["params"]["timed_out"] is True
    assert identity_rows[2]["params"]["late_result"] is True


class EventSink:
    def __init__(self):
        self.events = []

    def emit(self, event, *, operation, result=None, params=None):
        self.events.append((event, operation, result, params or {}))


def test_enrollment_observability_covers_start_attempt_completion_and_termination(tmp_path):
    store = EnrollmentSessionStore(tmp_path / "router.db")
    store.initialize()
    events = EventSink()
    service = EnrollmentService(store, event_sink=events)

    completed = service.start("nicola", "speaker-a", "it-IT", target_count=1)
    service.record_attempt(completed.session_id, "ACCEPTED", sample_id="sample-1")
    terminated = service.start("nicola", "speaker-b", "it-IT", target_count=2)
    service.record_attempt(terminated.session_id, "REJECTED", reason_code="TOO_SHORT")
    service.terminate(terminated.session_id, "user_cancelled")

    assert [item[0] for item in events.events] == [
        "enrollment.started",
        "enrollment.sample.accepted",
        "enrollment.completed",
        "enrollment.started",
        "enrollment.sample.rejected",
        "enrollment.terminated",
    ]
    assert events.events[1][3]["sample_id"] == "sample-1"
    assert events.events[4][3]["reason_code"] == "TOO_SHORT"


def test_wake_word_observability_records_terminal_outcome_and_completion(tmp_path):
    store = WakeWordCaptureSessionStore(tmp_path / "router.db")
    store.initialize()
    events = EventSink()
    service = WakeWordCaptureService(store, event_sink=events)

    capture = service.start("nicola", "speaker-a", "it-IT", "Nyra")
    service.complete(capture.session_id, "ACCEPTED", sample_id="wake-1")

    assert [item[0] for item in events.events] == [
        "wake_word.capture.started",
        "wake_word.capture.accepted",
        "wake_word.capture.completed",
    ]
    assert events.events[1][3]["sample_id"] == "wake-1"
    assert events.events[2][2] == "ACCEPTED"


@pytest.mark.asyncio
async def test_audio_start_records_enrollment_capture_started():
    class Sink:
        async def start(self, metadata):
            pass

        async def chunk(self, stream_id, payload):
            pass

        async def end(self, stream_id):
            return {"status": "REJECTED", "reason_code": "TOO_SHORT"}

        async def abort(self, stream_id, reason):
            pass

    events = EventSink()
    relay = CorrelatedIdentityAudioSink(Sink(), event_sink=events)
    metadata = AudioStreamStart(
        audio_stream_id="aud-1",
        purpose=AudioStreamPurpose.ENROLLMENT,
        session_id=None,
        request_id=None,
        source_id="speaker-a",
        user_id="nicola",
        enrollment_session_id="enr-1",
        trace_id=new_trace_id(),
        span_id=new_span_id("ROUTER", "audio_relay"),
    )

    await relay.start(metadata)

    assert events.events == [
        (
            "enrollment.capture.started",
            "enrollment",
            None,
            {
                "enrollment_session_id": "enr-1",
                "source_id": "speaker-a",
                "profile_user_id": "nicola",
                "audio_stream_id": "aud-1",
            },
        )
    ]
