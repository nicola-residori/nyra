from __future__ import annotations
import json
from shared.protocol.llm import LlmRequest

def semantic_messages(request:LlmRequest):
    payload={"language":request.context.language,"input":request.context.current_user_input,"context":request.context.model_dump(mode="json")}
    return ({"role":"user","content":json.dumps(payload,separators=(",",":"))},)

def reasoning_messages(request:LlmRequest):
    payload={
        "language":request.context.language,
        "input":request.context.current_user_input,
        "context":request.context.model_dump(mode="json"),
        "capability_results":[item.model_dump(mode="json") for item in request.capability_results],
    }
    return ({"role":"user","content":json.dumps(payload,separators=(",",":"))},)
