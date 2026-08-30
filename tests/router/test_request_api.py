from pathlib import Path
from fastapi.testclient import TestClient
from router.app import create_app
from router.config import RouterSettings
from router.lifecycle.service import LifecycleDecision, ContextResult, SkillMatch
from router.observability.ids import generate_request_id, generate_session_id


class Identity:
    async def identify(self, request, trace_id): return "user-a"
class Context:
    async def resolve(self, request, identity_user_id): return ContextResult(data={}, semantic_memory_required=False)
class Memory:
    async def search(self, request, identity_user_id, context): return {}
class Skill:
    async def check(self, request, context, memory, pending_state): return SkillMatch(True,"x")
    async def execute(self, match, request, context, memory, pending_state): return LifecycleDecision.completed("Done.")
class Llm:
    async def reason(self, request, context, memory, pending_state): return LifecycleDecision.completed("LLM.")


def payload():
    return {"type":"ha_assist","session_id":generate_session_id(),"request_id":generate_request_id(),"language":"it",
            "identity":{"user_id":"user-a","provider":"home_assistant","confidence":1.0},"input":{"text":"turn on the light"}}


def test_request_endpoint_validates_auth_and_returns_trace(tmp_path: Path):
    settings=RouterSettings(database_path=tmp_path/"router.db", ingress_token="secret")
    app=create_app(settings)
    with TestClient(app) as client:
        app.state.lifecycle.identity_port=Identity(); app.state.lifecycle.context_port=Context(); app.state.lifecycle.memory_port=Memory(); app.state.lifecycle.skill_port=Skill(); app.state.lifecycle.llm_port=Llm()
        assert client.post("/v1/requests",json=payload()).status_code==401
        response=client.post("/v1/requests",headers={"Authorization":"Bearer secret"},json=payload())
        assert response.status_code==200
        data=response.json(); assert data["status"]=="completed" and data["trace_id"].startswith("trc_")


def test_request_endpoint_maps_lifecycle_conflict_to_409(tmp_path: Path):
    app=create_app(RouterSettings(database_path=tmp_path/"router.db"))
    with TestClient(app) as client:
        app.state.lifecycle.identity_port=Identity(); app.state.lifecycle.context_port=Context(); app.state.lifecycle.memory_port=Memory(); app.state.lifecycle.skill_port=Skill(); app.state.lifecycle.llm_port=Llm()
        first=payload(); assert client.post("/v1/requests",json=first).status_code==200
        assert client.post("/v1/requests",json=first).status_code==409
