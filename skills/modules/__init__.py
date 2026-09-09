from __future__ import annotations

from skills.modules.identity import IdentityQuerySkill
from skills.registry import SkillDefinition, SkillRegistry


def register_builtin_skills(registry: SkillRegistry) -> None:
    identity = IdentityQuerySkill()
    registry.register(
        SkillDefinition(
            name=identity.name,
            priority=identity.priority,
            matcher=identity.matches,
            executor=identity.execute,
        )
    )
