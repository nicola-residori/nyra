from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from shared.protocol.skills import SkillCheckRequest


Matcher = Callable[[SkillCheckRequest], bool]
Executor = Callable[[Any], Any]


class SkillRegistryConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class SkillDefinition:
    name: str
    priority: int
    matcher: Matcher
    executor: Executor


@dataclass(frozen=True)
class SkillRegistryMatch:
    skill_name: str
    priority: int


class SkillRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, SkillDefinition] = {}

    def register(self, definition: SkillDefinition) -> None:
        if definition.name in self._definitions:
            raise SkillRegistryConflict(
                f"duplicate skill name: {definition.name}"
            )
        self._definitions[definition.name] = definition

    def check(self, request: SkillCheckRequest) -> SkillRegistryMatch | None:
        matches = [
            definition
            for definition in self._definitions.values()
            if definition.matcher(request)
        ]
        if not matches:
            return None

        matches.sort(key=lambda definition: (-definition.priority, definition.name))
        highest_priority = matches[0].priority
        highest = [
            definition
            for definition in matches
            if definition.priority == highest_priority
        ]
        if len(highest) > 1:
            names = ", ".join(definition.name for definition in highest)
            raise SkillRegistryConflict(
                f"ambiguous skills at priority {highest_priority}: {names}"
            )

        selected = highest[0]
        return SkillRegistryMatch(
            skill_name=selected.name,
            priority=selected.priority,
        )

    def get(self, name: str) -> SkillDefinition | None:
        return self._definitions.get(name)

    def is_ready(self) -> bool:
        priorities = [
            definition.priority for definition in self._definitions.values()
        ]
        return len(priorities) == len(set(priorities))
