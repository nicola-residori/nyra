from __future__ import annotations

from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from memory.app import create_app as create_memory_app
from memory.config import MemorySettings
from memory.embeddings import EmbeddingVector
from router.api.memory_admin import router
from router.memory_client import MemoryClient


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


class Directory:
    def get(self, provider, user_id):
        if user_id == "user-nicola":
            return SimpleNamespace(display_name="Nicola Residori")
        return None


def payload(content, key, **extra):
    return {
        "memory_type": "PREFERENCE",
        "scope": "USER",
        "owner_user_id": "user-nicola",
        "content": content,
        "source": "USER_EXPLICIT",
        "idempotency_key": key,
        **extra,
    }


def test_admin_duplicate_and_explicit_supersession_flow(tmp_path):
    memory_app = create_memory_app(
        MemorySettings(data_root=tmp_path / "memory"),
        embedding_provider=Embeddings(),
        event_sink=Events(),
    )
    memory_app.state.store.initialize()
    memory_client = MemoryClient(
        "http://memory.test", transport=httpx.ASGITransport(app=memory_app)
    )
    router_app = FastAPI()
    router_app.state.settings = SimpleNamespace(ingress_token=None)
    router_app.state.memory_client = memory_client
    router_app.state.user_directory = Directory()
    router_app.include_router(router)

    with TestClient(router_app) as client:
        first = client.post(
            "/v1/admin/memory/semantic",
            json=payload("Preferisco il caffè espresso.", "one"),
        )
        duplicate = client.post(
            "/v1/admin/memory/semantic",
            json=payload("  preferisco il caffè espresso. ", "two"),
        )
        replacement = client.post(
            "/v1/admin/memory/semantic",
            json=payload(
                "Preferisco il caffè lungo.",
                "three",
                supersedes_memory_id=first.json()["memory"]["memory_id"],
            ),
        )
        listing = client.get(
            "/v1/admin/memory/semantic?scope=USER&owner_user_id=user-nicola"
        )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json()["admission"] == "DUPLICATE"
    assert duplicate.json()["memory"]["memory_id"] == first.json()["memory"]["memory_id"]
    assert replacement.status_code == 201
    assert replacement.json()["admission"] == "SUPERSEDES"
    assert replacement.json()["memory"]["owner_display_name"] == "Nicola Residori"
    assert listing.json()["total"] == 2
