from __future__ import annotations

import re

from router.lifecycle.service import LifecycleDecision, SkillMatch
from shared.protocol.memory import MemoryRequirement


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
    async def check(self, request, context, memory, pending_state):
        language = _language(request.language)
        matched = _normalized(request.input.text) in _QUERY_PHRASES[language]
        return SkillMatch(
            matched=matched,
            token="identity_query" if matched else None,
            memory_requirement=MemoryRequirement.NONE,
        )

    async def execute(self, match, request, context, memory, pending_state):
        if not match.matched or match.token != "identity_query":
            raise ValueError("identity query skill requires a matching request")
        language = _language(request.language)
        identity = context.data.get("identity") or {}
        display_name = identity.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            name = " ".join(display_name.split())
            text = f"Sei {name}." if language == "it" else f"You are {name}."
        else:
            text = _UNKNOWN_RESPONSES[language]
        return LifecycleDecision.completed(text)
