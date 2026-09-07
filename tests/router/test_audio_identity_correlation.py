from types import SimpleNamespace
import asyncio

import pytest

from router.audio_streaming import CorrelatedIdentityAudioSink
from router.speaker_identity import SpeakerIdentityOutcome
from shared.audio_streaming import AudioStreamPurpose, AudioStreamStart


class IdentitySink:
    def __init__(self, result):
        self.result = result

    async def start(self, metadata):
        pass

    async def chunk(self, audio_stream_id, payload):
        pass

    async def end(self, audio_stream_id):
        return self.result

    async def abort(self, audio_stream_id, reason):
        pass


def metadata(purpose=AudioStreamPurpose.IDENTIFICATION):
    return AudioStreamStart(
        audio_stream_id="aud-1",
        purpose=purpose,
        session_id="ses-1",
        request_id="req-1",
        source_id="nyra-mansarda",
        trace_id="trc-1",
        span_id="spn-1",
    )


def identified_result():
    return {
        "outcome": "IDENTIFIED",
        "identified_user_id": "user-nicola",
        "best_score": 0.91,
        "diagnostic_id": "diag-1",
        "reason_code": None,
    }


@pytest.mark.asyncio
async def test_identity_request_waits_for_correlated_audio_result():
    port = CorrelatedIdentityAudioSink(IdentitySink(identified_result()))
    await port.start(metadata())
    waiting = asyncio.create_task(
        port.identify(SimpleNamespace(request_id="req-1"), "trace-request")
    )
    await asyncio.sleep(0)

    await port.end("aud-1")

    result = await waiting
    assert result.outcome is SpeakerIdentityOutcome.IDENTIFIED
    assert result.identified_user_id == "user-nicola"


@pytest.mark.asyncio
async def test_audio_result_can_arrive_before_correlated_request():
    port = CorrelatedIdentityAudioSink(IdentitySink(identified_result()))
    await port.start(metadata())
    await port.end("aud-1")

    result = await port.identify(SimpleNamespace(request_id="req-1"), "trace-request")

    assert result.identified_user_id == "user-nicola"


@pytest.mark.asyncio
async def test_enrollment_result_is_not_exposed_as_request_identity():
    port = CorrelatedIdentityAudioSink(
        IdentitySink({"status": "ACCEPTED", "user_id": "user-nicola"}),
        wait_timeout_seconds=0.01,
    )
    enrollment = metadata(AudioStreamPurpose.ENROLLMENT)
    enrollment = AudioStreamStart(
        **{
            **enrollment.__dict__,
            "enrollment_session_id": "enr-1",
            "user_id": "user-nicola",
        }
    )
    await port.start(enrollment)
    await port.end("aud-1")

    assert await port.identify(SimpleNamespace(request_id="req-1"), "trace-request") is None
