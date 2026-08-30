from uuid import uuid4
import pytest
from pydantic import ValidationError
from shared.protocol.requests import ExecutionType, RequestStatus, CloseReason, NyraRequest, NyraRequestResponse
from router.observability.ids import generate_request_id, generate_session_id, generate_trace_id


def speaker_payload():
    return {
        "type": "ha_speaker",
        "session_id": generate_session_id(),
        "request_id": generate_request_id(),
        "language": "it",
        "source": {"id": "speaker-a", "area": "living-room"},
        "input": {"text": "turn on the light"},
    }


def test_ha_speaker_requires_session_and_request_ids():
    with pytest.raises(ValidationError):
        NyraRequest.model_validate({**speaker_payload(), "session_id": None})
    with pytest.raises(ValidationError):
        NyraRequest.model_validate({**speaker_payload(), "request_id": None})


def test_ha_speaker_accepts_source_without_identity():
    req = NyraRequest.model_validate(speaker_payload())
    assert req.type is ExecutionType.HA_SPEAKER
    assert req.source.area == "living-room"
    assert req.identity is None


def test_ha_assist_accepts_trusted_identity():
    req = NyraRequest.model_validate({**speaker_payload(), "type": "ha_assist", "source": None,
        "identity": {"user_id": "user-a", "provider": "home_assistant", "confidence": 1.0}})
    assert req.identity.user_id == "user-a"


def test_job_requires_null_session_and_request_ids():
    with pytest.raises(ValidationError):
        NyraRequest.model_validate({"type":"job","session_id":generate_session_id(),"request_id":None,"language":"it","input":{"text":"run"}})


def test_job_accepts_origin_request_id():
    origin = generate_request_id()
    req = NyraRequest.model_validate({"type":"job","session_id":None,"request_id":None,"origin_request_id":origin,"language":"it","input":{"text":"run"}})
    assert req.origin_request_id == origin


def test_unknown_execution_type_is_rejected():
    with pytest.raises(ValidationError):
        NyraRequest.model_validate({**speaker_payload(), "type": "unknown"})


def test_invalid_prefixed_uuid_is_rejected():
    with pytest.raises(ValidationError):
        NyraRequest.model_validate({**speaker_payload(), "session_id": "ses_not-a-uuid"})


def test_closed_response_requires_reason_and_allows_null_body():
    with pytest.raises(ValidationError):
        NyraRequestResponse(status=RequestStatus.CLOSED, session_id=generate_session_id(), request_id=generate_request_id(), trace_id=generate_trace_id())
    response = NyraRequestResponse(status=RequestStatus.CLOSED, session_id=generate_session_id(), request_id=generate_request_id(), trace_id=generate_trace_id(), close_reason=CloseReason.ALARM_DISMISSED, response=None)
    assert response.close_reason is CloseReason.ALARM_DISMISSED
