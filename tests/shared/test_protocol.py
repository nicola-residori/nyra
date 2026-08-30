import pytest
from pydantic import ValidationError
from shared.protocol.observability import LogRecord
from router.observability.ids import *

def base(): return dict(ct='ROUTER',level='INFO',kind='EVENT',event='X',session_id=generate_session_id(),request_id=generate_request_id(),trace_id=generate_trace_id(),span_id=generate_span_id('router','x'),payload={'a':[1]})
def test_protocol_preserves_json_and_validates():
    r=LogRecord(**base()); assert r.payload=={'a':[1]}
    with pytest.raises(ValidationError): LogRecord(**{**base(),'level':'NOPE'})
    with pytest.raises(ValidationError): LogRecord(**{**base(),'span_id':'bad'})


def test_observability_rejects_unprefixed_correlation_ids():
    import pytest
    from pydantic import ValidationError
    from shared.protocol.observability import LogRecord, LogLevel, LogKind
    from router.observability.ids import generate_span_id, generate_trace_id

    base = dict(
        ct="ROUTER",
        level=LogLevel.INFO,
        kind=LogKind.EVENT,
        event="TEST_EVENT",
        session_id=None,
        request_id=None,
        trace_id=generate_trace_id(),
        span_id=generate_span_id("router", "test"),
    )
    with pytest.raises(ValidationError):
        LogRecord(**{**base, "session_id": "550e8400-e29b-41d4-a716-446655440000"})
    with pytest.raises(ValidationError):
        LogRecord(**{**base, "request_id": "550e8400-e29b-41d4-a716-446655440000"})
    with pytest.raises(ValidationError):
        LogRecord(**{**base, "trace_id": "550e8400-e29b-41d4-a716-446655440000"})
