from fastapi.testclient import TestClient
from llm.app import create_app
from shared.protocol.semantic import SemanticResult
from shared.protocol.llm import ReasoningOutcome,ReasoningResult

class Service:
    async def semantic(self,request):
        return SemanticResult(intent="query")
    async def reason(self,request):
        return ReasoningResult(outcome=ReasoningOutcome.COMPLETED,reasoning_id="r1",response_text="ok")

def context():
    return {"language":"en","current_user_input":"hello","operational":{"trace_id":"trace-a"}}

def test_semantic_and_reason_endpoints_are_typed():
    client=TestClient(create_app(service=Service()))
    semantic=client.post("/v1/llm/semantic",json={"purpose":"SEMANTIC","context":context()})
    assert semantic.status_code==200 and semantic.json()["intent"]=="query"
    reason=client.post("/v1/llm/reason",json={"purpose":"REASONING","context":context()})
    assert reason.status_code==200 and reason.json()["outcome"]=="COMPLETED"

def test_memory_extraction_is_disabled():
    client=TestClient(create_app(service=Service()))
    response=client.post("/v1/llm/reason",json={"purpose":"MEMORY_EXTRACTION","context":context()})
    assert response.status_code==422

def test_provider_model_override_is_rejected():
    client=TestClient(create_app(service=Service()))
    payload={"purpose":"REASONING","context":context(),"provider":"openai","model":"x"}
    assert client.post("/v1/llm/reason",json=payload).status_code==422
