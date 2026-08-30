import re, secrets, uuid

def _prefixed(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4()}"

def generate_session_id() -> str: return _prefixed("ses")
def generate_request_id() -> str: return _prefixed("req")
def generate_trace_id() -> str: return _prefixed("trc")

def _norm_ct(value: str) -> str:
    return re.sub(r"[^A-Z0-9_-]+", "_", value.upper()).strip("_") or "UNKNOWN"

def _norm_op(value: str) -> str:
    value = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")
    return value or "operation"

def generate_span_id(ct: str, operation: str) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{_norm_ct(ct)}#{_norm_op(operation)}#{suffix}"
