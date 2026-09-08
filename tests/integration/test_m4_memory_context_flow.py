from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from admin.app import create_app as create_admin_app
from admin.client import RouterClient
from admin.config import AdminSettings
from memory.app import create_app as create_memory_app
from memory.config import MemorySettings
from memory.embeddings import EmbeddingVector
from router.api.memory_admin import router as memory_admin_router
from router.lifecycle.events import InteractionEventBroker
from router.lifecycle.service import LifecycleDecision, MemoryQuery, RequestLifecycleService, SkillMatch
from router.lifecycle.store import RequestStateStore
from router.memory_client import MemoryClient
from shared.protocol.ids import new_request_id, new_session_id
from shared.protocol.memory import MemoryRequirement
from shared.protocol.requests import NyraRequest
from fastapi import FastAPI


class Embeddings:
    provider_name = "test"
    model_name = "test-v1"

    def prepare(self):
        return None

    def embed(self, text):
        return EmbeddingVector(values=(1.0, 0.0), provider="test", model="test-v1")


class Events:
    def emit_record(self, record):
        return None


class Directory:
    def get(self, provider, user_id):
        names = {"user-a": "Nicola Residori", "user-b": "Altro Utente"}
        name = names.get(user_id)
        return SimpleNamespace(display_name=name) if name else None


class NoIdentity:
    async def identify(self, request, trace_id):
        raise AssertionError("trusted identity expected")


class RequiredMemorySkill:
    async def check(self, request, context, memory, pending_state):
        return SkillMatch(
            matched=True,
            token="preference",
            memory_requirement=MemoryRequirement.REQUIRED,
            memory_query=MemoryQuery(query="caffè", minimum_similarity=0),
        )

    async def execute(self, match, request, context, memory, pending_state):
        assert context.data["ALIAS"]["desk"]["target"] == "light.user-desk"
        assert {item["owner_user_id"] for item in memory["items"]} == {"user-a"}
        return LifecycleDecision.completed(memory["items"][0]["content"])


class NoLlm:
    async def reason(self, request, context, memory, pending_state):
        raise AssertionError("matched skill expected")


def request() -> NyraRequest:
    return NyraRequest.model_validate({
        "type": "ha_assist",
        "session_id": new_session_id(),
        "request_id": new_request_id(),
        "language": "it-IT",
        "identity": {
            "user_id": "user-a", "provider": "home_assistant",
            "confidence": 1, "display_name": "Nicola Residori",
        },
        "input": {"text": "desk"},
    })


@pytest.mark.asyncio
async def test_complete_m4_flow_preserves_precedence_isolation_gate_and_admin(tmp_path):
    memory_app = create_memory_app(
        MemorySettings(data_root=tmp_path / "memory"),
        embedding_provider=Embeddings(), event_sink=Events(),
    )
    memory_app.state.store.initialize()
    memory_client = MemoryClient(
        "http://memory", transport=httpx.ASGITransport(app=memory_app)
    )
    router_app = FastAPI()
    router_app.state.settings = SimpleNamespace(ingress_token=None)
    router_app.state.memory_client = memory_client
    router_app.state.user_directory = Directory()
    router_app.include_router(memory_admin_router)
    router_transport = httpx.ASGITransport(app=router_app)

    async with httpx.AsyncClient(base_url="http://router", transport=router_transport) as client:
        for scope, owner, target, key in (
            ("SYSTEM", None, "light.system-desk", "system-alias"),
            ("USER", "user-a", "light.user-desk", "user-alias"),
        ):
            response = await client.post("/v1/admin/memory/operational", json={
                "entry_type": "ALIAS", "scope": scope, "owner_user_id": owner,
                "key": "desk", "value": {"target": target}, "enabled": True,
                "idempotency_key": key,
            })
            assert response.status_code == 201
        for user, content, key in (
            ("user-a", "Preferisco il caffè espresso.", "memory-a"),
            ("user-b", "Preferisco il caffè filtro.", "memory-b"),
        ):
            response = await client.post("/v1/admin/memory/semantic", json={
                "memory_type": "PREFERENCE", "scope": "USER",
                "owner_user_id": user, "content": content,
                "source": "USER_EXPLICIT", "idempotency_key": key,
            })
            assert response.status_code == 201

    store = RequestStateStore(tmp_path / "router.sqlite3")
    store.initialize()
    lifecycle = RequestLifecycleService(
        store=store, broker=InteractionEventBroker(), identity_port=NoIdentity(),
        context_port=memory_client, memory_port=memory_client,
        skill_port=RequiredMemorySkill(), llm_port=NoLlm(),
    )
    result = await lifecycle.execute(request())
    assert result.response.text == "Preferisco il caffè espresso."

    admin_app = create_admin_app(
        AdminSettings(),
        RouterClient("http://router", transport=router_transport),
    )
    async with httpx.AsyncClient(
        base_url="http://admin", transport=httpx.ASGITransport(app=admin_app)
    ) as admin:
        page = await admin.get("/memory/semantic?scope=USER&owner_user_id=user-a&q=caff%C3%A8")
    assert page.status_code == 200
    assert "Nicola Residori" in page.text
    assert "user-a" in page.text
    assert "Preferisco il caffè espresso." in page.text
