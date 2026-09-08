from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from router.app import create_app
from router.config import RouterSettings
from router.identity_skill import IdentityQuerySkill
from router.lifecycle.service import ContextResult
from shared.protocol.ids import new_request_id, new_session_id
from shared.protocol.requests import NyraRequest, RequestStatus


def request(text: str, language: str) -> NyraRequest:
    return NyraRequest.model_validate({
        "type": "ha_speaker",
        "session_id": new_session_id(),
        "request_id": new_request_id(),
        "language": language,
        "source": {"id": "nyra-mansarda", "area": "mansarda"},
        "input": {"text": text},
    })


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "language", "expected"),
    [
        ("Chi sono?", "it-IT", "Sei Nicola Residori."),
        ("Who am I?", "en-US", "You are Nicola Residori."),
    ],
)
async def test_identity_query_uses_trusted_display_name(text, language, expected):
    skill = IdentityQuerySkill()
    item = request(text, language)
    context = ContextResult(data={
        "identity": {
            "user_id": "b1a7ab76eb9c44caa1971feaf657e9e2",
            "display_name": "Nicola Residori",
            "resolution_source": "SPEAKER_IDENTIFICATION",
        }
    })

    match = await skill.check(item, context, None, None)
    decision = await skill.execute(match, item, context, None, None)

    assert match.matched
    assert decision.status is RequestStatus.COMPLETED
    assert decision.text == expected
    assert context.data["identity"]["user_id"] not in decision.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("it-IT", "Non riesco a riconoscerti."),
        ("en-US", "I cannot identify you."),
    ],
)
async def test_identity_query_never_speaks_guest_or_a_technical_id(language, expected):
    skill = IdentityQuerySkill()
    item = request("chi sono" if language.startswith("it") else "who am i", language)
    context = ContextResult(data={
        "identity": {
            "user_id": "guest",
            "display_name": None,
            "resolution_source": "GUEST_FALLBACK",
        }
    })

    match = await skill.check(item, context, None, None)
    decision = await skill.execute(match, item, context, None, None)

    assert match.matched
    assert decision.text == expected
    assert "guest" not in decision.text.lower()


@pytest.mark.asyncio
async def test_identity_skill_ignores_unrelated_requests():
    skill = IdentityQuerySkill()
    item = request("che ore sono", "it-IT")

    match = await skill.check(item, ContextResult(data={}), None, None)

    assert not match.matched


def test_router_executes_identity_query_with_trusted_home_assistant_name(tmp_path):
    app = create_app(RouterSettings(database_path=tmp_path / "router.db"))
    with TestClient(app) as client:
        response = client.post("/v1/requests", json={
            "type": "ha_assist",
            "session_id": new_session_id(),
            "request_id": new_request_id(),
            "language": "it-IT",
            "source": {"id": "phone"},
            "identity": {
                "user_id": "ha-1",
                "provider": "home_assistant",
                "confidence": 1.0,
                "display_name": "Nicola Residori",
            },
            "input": {"text": "Chi sono?"},
        })

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["response"]["text"] == "Sei Nicola Residori."
