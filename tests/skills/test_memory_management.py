import pytest

from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCorrelation,
    SkillExecuteRequest,
    SkillOutcome,
)

def correlation():
    request_id = new_request_id()
    return SkillCorrelation(
        request_id=request_id,
        origin_request_id=request_id,
        trace_id=new_trace_id(),
    )


def request(text: str, language: str = "en", pending_state=None):
    return SkillCheckRequest(
        correlation=correlation(),
        text=text,
        language=language,
        context={},
        pending_state=pending_state,
    )


def test_remember_becomes_structured_candidate_without_scope_or_identity():
    from skills.modules.memory_management import MemoryManagementSkill
    skill = MemoryManagementSkill()
    req = request("remember that my preferred temperature is 21 degrees")

    match = skill.match(req)

    assert match.matched is True
    assert match.skill_name == "memory_management"
    assert match.metadata["operation"] == "REMEMBER"
    assert match.metadata["content"] == "my preferred temperature is 21 degrees"
    assert match.metadata["memory_type"] == "PREFERENCE"
    assert "scope" not in match.metadata
    assert "owner_user_id" not in match.metadata
    assert "user_id" not in match.metadata


def test_forget_is_destructive_lookup_request_not_immediate_delete():
    from skills.modules.memory_management import MemoryManagementSkill
    skill = MemoryManagementSkill()
    req = request("forget my preferred temperature")

    match = skill.match(req)

    assert match.metadata == {
        "operation": "FORGET",
        "query": "my preferred temperature",
        "content": None,
        "replacement": None,
        "memory_type": "NOTE",
    }


def test_supersede_becomes_structured_candidate():
    from skills.modules.memory_management import MemoryManagementSkill
    skill = MemoryManagementSkill()
    req = request("replace my preferred temperature with 22 degrees")

    match = skill.match(req)

    assert match.metadata["operation"] == "SUPERSEDE"
    assert match.metadata["query"] == "my preferred temperature"
    assert match.metadata["replacement"] == "my preferred temperature is 22 degrees"
    assert match.metadata["memory_type"] == "PREFERENCE"


def test_unrelated_prose_is_miss():
    from skills.modules.memory_management import MemoryManagementSkill
    skill = MemoryManagementSkill()
    req = request("what is the preferred temperature?")

    assert skill.matches(req) is False
    assert skill.match(req).matched is False


def test_text_cannot_choose_another_users_identity_or_scope():
    from skills.modules.memory_management import MemoryManagementSkill
    skill = MemoryManagementSkill()
    req = request("remember that for user bob the preferred temperature is 19 degrees")

    match = skill.match(req)

    assert match.metadata["operation"] == "REMEMBER"
    assert all(
        key not in match.metadata
        for key in ("scope", "owner_user_id", "user_id")
    )


@pytest.mark.asyncio
async def test_execute_emits_typed_router_operation_only():
    from skills.modules.memory_management import MemoryManagementSkill
    skill = MemoryManagementSkill()
    req = request("forget my preferred temperature")
    match = skill.match(req)

    response = await skill.execute(
        SkillExecuteRequest(
            correlation=req.correlation,
            match=match,
            text=req.text,
            language=req.language,
            context={},
        )
    )

    assert response.outcome is SkillOutcome.HANDLED
    operation = response.result["router_operation"]
    assert operation["kind"] == "MEMORY_MANAGEMENT"
    assert operation["operation"] == "FORGET"
    assert operation["query"] == "my preferred temperature"
    assert "scope" not in operation
    assert "owner_user_id" not in operation


@pytest.mark.asyncio
async def test_pending_destructive_clarification_emits_selection_only():
    from skills.modules.memory_management import MemoryManagementSkill
    skill = MemoryManagementSkill()
    pending = {
        "kind": "memory_management_clarification",
        "operation": "FORGET",
        "candidates": [
            {"memory_id": "mem_one", "content": "preferred temperature is 21"},
            {"memory_id": "mem_two", "content": "preferred temperature upstairs is 19"},
        ],
    }
    req = request("the second", pending_state=pending)

    assert skill.matches(req) is True
    match = skill.match(req)
    response = await skill.execute(
        SkillExecuteRequest(
            correlation=req.correlation,
            match=match,
            text=req.text,
            language=req.language,
            context={},
            pending_state=pending,
        )
    )

    assert response.result["router_operation"] == {
        "kind": "MEMORY_MANAGEMENT",
        "operation": "RESOLVE_CLARIFICATION",
        "selection": "the second",
    }
