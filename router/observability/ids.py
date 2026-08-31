from shared.protocol.ids import new_request_id, new_session_id, new_span_id, new_trace_id

generate_session_id = new_session_id
generate_request_id = new_request_id
generate_trace_id = new_trace_id
generate_span_id = new_span_id

__all__ = ["generate_session_id", "generate_request_id", "generate_trace_id", "generate_span_id"]
