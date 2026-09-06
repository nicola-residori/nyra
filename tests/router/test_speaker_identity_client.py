from __future__ import annotations

import importlib
from dataclasses import dataclass

import pytest


def identity_module():
    return importlib.import_module("router.speaker_identity")


@dataclass
class FakeTransport:
    response: dict
    captured_path: str | None = None
    captured_payload: dict | None = None

    async def post_json(self, path: str, payload: dict) -> dict:
        self.captured_path = path
        self.captured_payload = payload
        return self.response


def request():
    module = identity_module()
    return module.SpeakerIdentityRequest(
        audio_stream_id="audio-123",
        session_id="session-123",
        request_id="request-123",
        source_id="speaker-kitchen",
        trace_id="trace-123",
        span_id="span-123",
    )


@pytest.mark.asyncio
async def test_identified_response_is_parsed_as_minimal_realtime_dto():
    module = identity_module()
    transport = FakeTransport({
        "outcome": "IDENTIFIED",
        "identified_user_id": "alice",
        "best_score": .83,
        "diagnostic_id": "diag-1",
        "reason_code": None,
        "candidate_scores": {"alice": .83, "bob": .52},
    })
    client = module.SpeakerIdentityClient(transport)

    result = await client.identify(request())

    assert result.outcome is module.SpeakerIdentityOutcome.IDENTIFIED
    assert result.identified_user_id == "alice"
    assert result.best_score == .83
    assert result.diagnostic_id == "diag-1"
    assert result.reason_code is None
    assert not hasattr(result, "candidate_scores")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_name"),
    [
        ({
            "outcome": "NOT_RECOGNIZED",
            "identified_user_id": None,
            "best_score": .39,
            "diagnostic_id": "diag-2",
            "reason_code": "BELOW_THRESHOLD",
        }, "NOT_RECOGNIZED"),
        ({
            "outcome": "FAILED",
            "identified_user_id": None,
            "best_score": None,
            "diagnostic_id": "diag-3",
            "reason_code": "MODEL_UNAVAILABLE",
        }, "FAILED"),
    ],
)
async def test_non_identified_outcomes_are_typed(payload, expected_name):
    module = identity_module()
    result = await module.SpeakerIdentityClient(FakeTransport(payload)).identify(request())
    assert result.outcome is getattr(module.SpeakerIdentityOutcome, expected_name)
    assert result.identified_user_id is None


@pytest.mark.asyncio
async def test_full_correlation_is_transported_unchanged():
    module = identity_module()
    transport = FakeTransport({
        "outcome": "NOT_RECOGNIZED",
        "identified_user_id": None,
        "best_score": None,
        "diagnostic_id": "diag",
        "reason_code": "NO_PROFILES",
    })

    await module.SpeakerIdentityClient(transport).identify(request())

    assert transport.captured_path == "/v1/identify"
    assert transport.captured_payload == {
        "audio_stream_id": "audio-123",
        "session_id": "session-123",
        "request_id": "request-123",
        "source_id": "speaker-kitchen",
        "trace_id": "trace-123",
        "span_id": "span-123",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {
            "outcome": "GUEST",
            "identified_user_id": None,
            "best_score": None,
            "diagnostic_id": "diag",
            "reason_code": None,
        },
        {
            "outcome": "IDENTIFIED",
            "identified_user_id": "guest",
            "best_score": .90,
            "diagnostic_id": "diag",
            "reason_code": None,
        },
        {
            "outcome": "NOT_RECOGNIZED",
            "identified_user_id": "alice",
            "best_score": .30,
            "diagnostic_id": "diag",
            "reason_code": "BELOW_THRESHOLD",
        },
        {
            "outcome": "UNKNOWN",
            "identified_user_id": None,
            "best_score": None,
            "diagnostic_id": "diag",
            "reason_code": None,
        },
    ],
)
async def test_invalid_or_policy_leaking_responses_are_rejected(payload):
    module = identity_module()
    with pytest.raises(module.InvalidSpeakerIdentityResponse):
        await module.SpeakerIdentityClient(FakeTransport(payload)).identify(request())


@pytest.mark.asyncio
async def test_admin_diagnostic_detail_is_separate_from_realtime_decision():
    module = identity_module()
    transport = FakeTransport({
        "diagnostic_id": "diag-9",
        "outcome": "IDENTIFIED",
        "identified_user_id": "alice",
        "best_score": .81,
        "reason_code": None,
        "candidate_scores": [
            {"user_id": "alice", "score": .81, "rank": 1},
            {"user_id": "bob", "score": .55, "rank": 2},
        ],
    })
    client = module.SpeakerIdentityClient(transport)

    detail = await client.get_diagnostic("diag-9")

    assert transport.captured_path == "/v1/diagnostics/diag-9"
    assert detail.diagnostic_id == "diag-9"
    assert [(x.user_id, x.score, x.rank) for x in detail.candidates] == [
        ("alice", .81, 1),
        ("bob", .55, 2),
    ]
