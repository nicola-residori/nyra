from __future__ import annotations

import re

from shared.protocol.memory import MemoryRequirement
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillExecuteRequest,
    SkillMatch,
)


_QUERY_PHRASES = {
    "it": {
        "chi sono",
        "chi sono io",
        "dimmi chi sono",
        "sai chi sono",
    },
    "en": {
        "who am i",
        "tell me who i am",
        "do you know who i am",
    },
}

_UNKNOWN_RESPONSES = {
    "it": "Non riesco a riconoscerti.",
    "en": "I cannot identify you.",
}


def _language(value: str) -> str:
    language = value.split("-", 1)[0].lower()
    return language if language in _QUERY_PHRASES else "en"


def _normalized(value: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", value.casefold()).split())


class IdentityQuerySkill:
    name = "identity_query"
    priority = 100

    def matches(self, request: SkillCheckRequest) -> bool:
        language = _language(request.language)
        return _normalized(request.text) in _QUERY_PHRASES[language]

    def match(self, request: SkillCheckRequest | None = None) -> SkillMatch:
        return SkillMatch(
            matched=True,
            skill_name=self.name,
            token=self.name,
            memory_requirement=MemoryRequirement.NONE,
        )

    def execute(self, request: SkillExecuteRequest) -> str:
        identity = request.context.get("identity") or {}
        display_name = identity.get("display_name")
        language = _language(request.language)

        if isinstance(display_name, str) and display_name.strip():
            name = " ".join(display_name.split())
            return f"Sei {name}." if language == "it" else f"You are {name}."

        return _UNKNOWN_RESPONSES[language]
