from __future__ import annotations

from dataclasses import dataclass

import pytest

from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import SkillCheckRequest, SkillCorrelation
from skills.registry import (
    SkillDefinition,
    SkillRegistry,
    SkillRegistryConflict,
)


@dataclass
class FakeSkill:
    name: str
    priority: int
    matches: bool

    def matcher(self, request: SkillCheckRequest) -> bool:
        return self.matches

    def executor(self, request):
        return {"skill": self.name}


def request() -> SkillCheckRequest:
    return SkillCheckRequest(
        correlation=SkillCorrelation(
            request_id=new_request_id(),
            trace_id=new_trace_id(),
        ),
        text="turn on the lamp",
        language="en",
    )


def definition(name: str, *, priority: int, matches: bool) -> SkillDefinition:
    fake = FakeSkill(name=name, priority=priority, matches=matches)
    return SkillDefinition(
        name=fake.name,
        priority=fake.priority,
        matcher=fake.matcher,
        executor=fake.executor,
    )


def test_registry_uses_highest_priority_match_deterministically():
    registry = SkillRegistry()
    registry.register(definition("low", priority=10, matches=True))
    registry.register(definition("high", priority=100, matches=True))

    match = registry.check(request())

    assert match is not None
    assert match.skill_name == "high"
    assert match.priority == 100


def test_duplicate_stable_name_is_rejected():
    registry = SkillRegistry()
    registry.register(definition("same", priority=10, matches=False))

    with pytest.raises(SkillRegistryConflict):
        registry.register(definition("same", priority=20, matches=True))


def test_equal_priority_conflict_is_rejected_and_readiness_fails():
    registry = SkillRegistry()
    registry.register(definition("a", priority=100, matches=True))
    registry.register(definition("b", priority=100, matches=True))

    assert registry.is_ready() is False
    with pytest.raises(SkillRegistryConflict):
        registry.check(request())


def test_router_visible_match_exposes_metadata_not_module_reference():
    registry = SkillRegistry()
    registry.register(definition("identity_query", priority=50, matches=True))

    match = registry.check(request())

    assert match is not None
    assert match.skill_name == "identity_query"
    assert match.priority == 50
    assert not hasattr(match, "matcher")
    assert not hasattr(match, "executor")
    assert not hasattr(match, "module")
