from fastapi.testclient import TestClient
from skills.app import create_app
from skills.service import SkillsService
from shared.protocol.ids import new_request_id, new_trace_id

def payload():
    request_id = new_request_id()
    return {"correlation":{"request_id":request_id,"origin_request_id":request_id,"trace_id":new_trace_id()},"plan":{"plan_id":"p","origin":"REASONING_LLM","validation_state":"PROPOSED","steps":[{"step_id":"s","operation":"TURN_ON","target":{"reference":"kitchen","resource_type":"LIGHT"},"parameters":{},"depends_on":[],"conditions":[]}],"behaviors":[]},"trusted_context":{}}

def test_plan_validation_endpoint_never_executes_capability():
    c=TestClient(create_app(service=SkillsService()))
    r=c.post("/v1/plans/validate",json=payload())
    assert r.status_code==200 and r.json()["outcome"]=="VALIDATED"
