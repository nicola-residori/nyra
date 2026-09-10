from __future__ import annotations

from skills.modules.delayed_action import DelayedActionSkill
from skills.modules.home_assistant import (
    HomeAssistantActionSkill,
    RouterHomeAssistantCapabilityClient,
)
from skills.modules.identity import IdentityQuerySkill
from skills.registry import SkillDefinition, SkillRegistry


def register_builtin_skills(
    registry: SkillRegistry,
    *,
    home_assistant_capability: RouterHomeAssistantCapabilityClient | None = None,
    job_scheduler=None,
) -> None:
    identity = IdentityQuerySkill()
    registry.register(
        SkillDefinition(
            name=identity.name,
            priority=identity.priority,
            matcher=identity.matches,
            executor=identity.execute,
        )
    )

    if home_assistant_capability is not None:
        if job_scheduler is not None:
            delayed_action = DelayedActionSkill(
                home_assistant_capability,
                job_scheduler,
            )
            registry.register(
                SkillDefinition(
                    name=delayed_action.name,
                    priority=delayed_action.priority,
                    matcher=delayed_action.matches,
                    executor=delayed_action.execute,
                )
            )

        home_assistant = HomeAssistantActionSkill(home_assistant_capability)
        registry.register(
            SkillDefinition(
                name=home_assistant.name,
                priority=home_assistant.priority,
                matcher=home_assistant.matches,
                executor=home_assistant.execute,
            )
        )
