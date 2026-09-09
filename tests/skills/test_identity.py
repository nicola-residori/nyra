from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from skills.app import create_app
from skills.modules.identity import IdentityQuerySkill
from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.memory import MemoryRequirement
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCorrelation,
    SkillExecuteRequest,
    SkillOutcome,
)


def correlation() -> SkillCorrelation:
    return SkillCorrelation(
        request_id=new_request_id(),
        trace_id=new_trace_id(),
    )


def check_request(
    text: str,
    language: str,
    *,
    display_name: str | None,
    user_id: str = "ha-1",
    resolution_source: str = "TRUSTED_HA_IDENTITY",
) -> SkillCheckRequest:
    return SkillCheckRequest(
        correlation=correlation(),
        text=text,
        language=language,
        context={
            "identity": {
                "user_id": user_id,
                "display_name": display_name,
                "resolution_source": resolution_source,
            }
        },
    )


@pytest.mark.parametrize(
    ("text", "language", "display_name", "resolution_source", "expected"),
    [
        (
            "Chi sono?",
            "it-IT",
            "Nicola Residori",
            "TRUSTED_HA_IDENTITY",
            "Sei Nicola Residori.",
        ),
        (
            "Who am I?",
            "en-US",
            "Nicola Residori",
            "SPEAKER_IDENTIFICATION",
            "You are Nicola Residori.",
        ),
    ],
)
def test_identity_query_preserves_trusted_identity_and_localization(
    text,
    language,
    display_name,
    resolution_source,
    expected,
):
    skill = IdentityQuerySkill()
    check = check_request(
        text,
        language,
        display_name=display_name,
        resolution_source=resolution_source,
    )

    assert skill.matches(check) is True

    result = skill.execute(
        SkillExecuteRequest(
            correlation=check.correlation,
            match=skill.match(),
            text=check.text,
            language=check.language,
            context=check.context,
        )
    )

    assert result == expected
    assert check.context["identity"]["user_id"] not in result


@pytest.mark.parametrize(
    ("language", "text", "expected"),
    [
        ("it-IT", "chi sono", "Non riesco a riconoscerti."),
        ("en-US", "who am i", "I cannot identify you."),
    ],
)
def test_identity_query_is_guest_safe(language, text, expected):
    skill = IdentityQuerySkill()
    check = check_request(
        text,
        language,
        display_name=None,
        user_id="guest",
        resolution_source="GUEST_FALLBACK",
    )

    result = skill.execute(
        SkillExecuteRequest(
            correlation=check.correlation,
            match=skill.match(),
            text=check.text,
            language=check.language,
            context=check.context,
        )
    )

    assert result == expected
    assert "guest" not in result.lower()


def test_identity_query_declares_no_semantic_memory():
    skill = IdentityQuerySkill()

    assert skill.match().memory_requirement is MemoryRequirement.NONE


def test_identity_query_ignores_unrelated_requests():
    skill = IdentityQuerySkill()
    check = check_request(
        "che ore sono",
        "it-IT",
        display_name="Nicola Residori",
    )

    assert skill.matches(check) is False


def test_identity_skill_is_wired_through_private_registry_and_http_api():
    client = TestClient(create_app())
    check_payload = check_request(
        "Chi sono?",
        "it-IT",
        display_name="Nicola Residori",
    )

    check_response = client.post(
        "/v1/skills/check",
        json=check_payload.model_dump(mode="json"),
    )

    assert check_response.status_code == 200
    checked = check_response.json()
    assert checked["outcome"] == SkillOutcome.HANDLED.value
    assert checked["match"]["matched"] is True
    assert checked["match"]["skill_name"] == "identity_query"
    assert checked["match"]["memory_requirement"] == MemoryRequirement.NONE.value

    execute_payload = SkillExecuteRequest(
        correlation=check_payload.correlation,
        match=checked["match"],
        text=check_payload.text,
        language=check_payload.language,
        context=check_payload.context,
    )
    execute_response = client.post(
        "/v1/skills/execute",
        json=execute_payload.model_dump(mode="json"),
    )

    assert execute_response.status_code == 200
    executed = execute_response.json()
    assert executed["outcome"] == SkillOutcome.HANDLED.value
    assert executed["text"] == "Sei Nicola Residori."


def test_skills_http_returns_miss_for_unrelated_request():
    client = TestClient(create_app())
    payload = check_request(
        "che ore sono",
        "it-IT",
        display_name="Nicola Residori",
    )

    response = client.post(
        "/v1/skills/check",
        json=payload.model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == SkillOutcome.MISS.value
    assert response.json()["match"] is None
