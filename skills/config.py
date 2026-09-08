from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class SkillsSettings:
    host: str = "0.0.0.0"
    port: int = 8090

    @classmethod
    def load(cls) -> "SkillsSettings":
        return cls(
            host=os.getenv("NYRA_SKILLS_HOST", "0.0.0.0"),
            port=int(os.getenv("NYRA_SKILLS_PORT", "8090")),
        )
