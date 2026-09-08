from __future__ import annotations

import httpx
import pytest

from memory.app import create_app as create_memory_app
from memory.config import MemorySettings
from memory.embeddings import EmbeddingVector
from router.lifecycle.events import InteractionEventBroker
from router.lifecycle.service import (
    LifecycleDecision,
    MemoryQuery,
    RequestLifecycleService,
    SkillMatch,
)
from router.lifecycle.store import RequestStateStore
from router.memory_client import MemoryClient
from shared.protocol.ids import new_request_id, new_session_id
from shared.protocol.memory import MemoryRequirement, SemanticMemoryCreate
from shared.protocol.requests import NyraRequest


class Embeddings:
    provider_name = "test"
    model_name = "test-v1"

    def prepare(self):
        return None

    def embed(self, text):
        return EmbeddingVector(
            values=(1.0, 0.0), provider=self.provider_name, model=self.model_name
        )


class Events:
    def emit_record(self, record):
        return None


class Identity:
    async def identify(self, request, trace_id):
        raise AssertionError("trusted HA identity must bypass speaker identification")


class MemorySkill:
    def __init__(self):
        self.memory = None

    async def check(self, request, context, memory, pending_state):
        return SkillMatch(
            matched=True,
            token="preference",
            memory_requirement=MemoryRequirement.REQUIRED,
            memory_query=MemoryQuery(query="caffè", minimum_similarity=0),
        )

    async def execute(self, match, request, context, memory, pending_state):
        self.memory = memory
        return LifecycleDecision.completed(memory["items"][0]["content"])


class Llm:
    async def reason(self, request, context, memory, pending_state):
        raise AssertionError("matched skill must execute locally")


@pytest.mark.asyncio
async def test_router_enriches_matched_skill_with_identity_scoped_memory(tmp_path):
    memory_app = create_memory_app(
        MemorySettings(data_root=tmp_path / "memory"),
        embedding_provider=Embeddings(),
        event_sink=Events(),
    )
    memory_app.state.store.initialize()
    memory_app.state.semantic_memory.create(SemanticMemoryCreate(
        memory_type="PREFERENCE",
        scope="USER",
        owner_user_id="user-nicola",
        content="Preferisco il caffè espresso.",
        source="USER_EXPLICIT",
        idempotency_key="preference-1",
    ))
    client = MemoryClient(
        "http://memory.test",
        transport=httpx.ASGITransport(app=memory_app),
    )
    request_store = RequestStateStore(tmp_path / "router.sqlite3")
    request_store.initialize()
    skill = MemorySkill()
    lifecycle = RequestLifecycleService(
        store=request_store,
        broker=InteractionEventBroker(),
        identity_port=Identity(),
        context_port=client,
        memory_port=client,
        skill_port=skill,
        llm_port=Llm(),
    )
    request = NyraRequest.model_validate({
        "type": "ha_assist",
        "session_id": new_session_id(),
        "request_id": new_request_id(),
        "language": "it-IT",
        "identity": {
            "user_id": "user-nicola",
            "provider": "home_assistant",
            "confidence": 1,
            "display_name": "Nicola",
        },
        "input": {"text": "Che caffè preferisco?"},
    })

    response = await lifecycle.execute(request)

    assert response.response.text == "Preferisco il caffè espresso."
    assert skill.memory["items"][0]["owner_user_id"] == "user-nicola"
