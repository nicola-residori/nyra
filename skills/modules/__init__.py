from __future__ import annotations

from skills.modules.behavior import BehaviorSkill
from skills.modules.delayed_action import DelayedActionSkill
from skills.modules.home_assistant import (
    HomeAssistantActionSkill,
    RouterHomeAssistantCapabilityClient,
)
from skills.modules.identity import IdentityQuerySkill
from skills.modules.memory_management import MemoryManagementSkill
from skills.registry import SkillDefinition, SkillRegistry


def register_builtin_skills(
    registry: SkillRegistry,
    *,
    home_assistant_capability: RouterHomeAssistantCapabilityClient | None = None,
    job_scheduler=None,
    alert_timezone="Europe/Rome",
    alert_max_seconds=60,
) -> None:
    if home_assistant_capability is not None:
        from skills.modules.music import MusicSkill
        music = MusicSkill(home_assistant_capability)
        registry.register(SkillDefinition(name=music.name,priority=music.priority,matcher=music.matches,executor=music.execute))
    if job_scheduler is not None:
        from skills.modules.voice_alerts import VoiceAlertsSkill

        alerts = VoiceAlertsSkill(
            job_scheduler, timezone_name=alert_timezone, max_seconds=alert_max_seconds
        )
        registry.register(
            SkillDefinition(
                name=alerts.name,
                priority=alerts.priority,
                matcher=alerts.matches,
                executor=alerts.execute,
            )
        )
    memory_management = MemoryManagementSkill()
    registry.register(
        SkillDefinition(
            name=memory_management.name,
            priority=memory_management.priority,
            matcher=memory_management.matches,
            executor=memory_management.execute,
        )
    )

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

        behavior = BehaviorSkill(home_assistant_capability)
        registry.register(
            SkillDefinition(
                name=behavior.name,
                priority=behavior.priority,
                matcher=behavior.matches,
                executor=behavior.execute,
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
