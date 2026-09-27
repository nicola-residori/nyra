from __future__ import annotations
import json
from shared.protocol.llm import LlmRequest

def semantic_messages(request:LlmRequest):
    payload={"language":request.context.language,"input":request.context.current_user_input,"context":request.context.model_dump(mode="json")}
    if request.context.operational.get("mode")=="skill_routing":
        contract=("Return only SemanticResult JSON. For executable device control use canonical operation values TURN_ON, TURN_OFF, OPEN, CLOSE, TOGGLE, SET, INCREASE, DECREASE, START, STOP, TRIGGER and canonical target.kind values LIGHT, SWITCH, COVER, CLIMATE, MEDIA_PLAYER, SCRIPT, SCENE, AUTOMATION. Preserve target wording in target.reference and put an explicitly stated room/area in target.area. Always provide confidence.score from 0.0 to 1.0 for skill routing; use lower confidence when the command, target kind, operation, or area is uncertain. Never invent area, entity id, operation, resource kind, trigger, condition, temporal constraint, or parameter.")
        payload["contract"]=contract
    return ({"role":"user","content":json.dumps(payload,separators=(",",":"))},)

def reasoning_messages(request:LlmRequest):
    payload={
        "language":request.context.language,
        "input":request.context.current_user_input,
        "context":request.context.model_dump(mode="json"),
        "capability_results":[item.model_dump(mode="json") for item in request.capability_results],
    }
    return ({"role":"user","content":json.dumps(payload,separators=(",",":"))},)
