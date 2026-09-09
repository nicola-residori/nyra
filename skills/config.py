from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class SkillsSettings:
    host: str = "0.0.0.0"
    port: int = 8090
    router_url: str | None = None
    router_timeout_seconds: float = 3.0

    @classmethod
    def load(cls) -> "SkillsSettings":
        return cls(
            host=os.getenv("NYRA_SKILLS_HOST", "0.0.0.0"),
            port=int(os.getenv("NYRA_SKILLS_PORT", "8090")),
            router_url=os.getenv("NYRA_ROUTER_URL"),
            router_timeout_seconds=float(
                os.getenv("NYRA_ROUTER_TIMEOUT_SECONDS", "3.0")
            ),
        )
