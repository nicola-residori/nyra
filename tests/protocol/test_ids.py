import re
import pytest
from pydantic import ValidationError
from shared.protocol.ids import CorrelationContext, new_request_id, new_session_id, new_span_id, new_trace_id
UUID_ID = re.compile(r"^(ses|req|trc)_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
def test_uuid_ids_use_canonical_prefix_and_uuid4():
    assert UUID_ID.match(new_session_id()); assert UUID_ID.match(new_request_id()); assert UUID_ID.match(new_trace_id())
def test_span_id_uses_component_operation_and_eight_uppercase_chars():
    assert re.fullmatch(r"ROUTER#request_lifecycle#[A-Z0-9]{8}", new_span_id("ROUTER","request_lifecycle"))
def test_correlation_accepts_interactive_delayed_and_system_work():
    trace=new_trace_id(); interactive=CorrelationContext(request_id=new_request_id(),trace_id=trace); assert interactive.origin_request_id is None
    delayed=CorrelationContext(origin_request_id=new_request_id(),trace_id=trace); assert delayed.request_id is None
    system=CorrelationContext(trace_id=trace); assert system.request_id is None and system.origin_request_id is None
def test_correlation_rejects_malformed_ids_and_has_no_session_id():
    assert "session_id" not in CorrelationContext.model_fields
    with pytest.raises(ValidationError): CorrelationContext(trace_id="bad")
    with pytest.raises(ValidationError): CorrelationContext(trace_id=new_trace_id(), request_id="req_bad")
    with pytest.raises(ValidationError): CorrelationContext(trace_id=new_trace_id(), parent_span_id="bad")
