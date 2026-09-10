from __future__ import annotations

import re
from dataclasses import dataclass

from shared.protocol.common import ErrorDetail
from shared.protocol.memory import MemoryRequirement, SemanticMemoryType
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillExecuteRequest,
    SkillExecuteResponse,
    SkillMatch,
    SkillOutcome,
)


@dataclass(frozen=True)
class ParsedMemoryIntent:
    operation: str
    query: str | None = None
    content: str | None = None
    replacement: str | None = None
    memory_type: SemanticMemoryType = SemanticMemoryType.NOTE


def _lang(language: str) -> str:
    return "it" if language.split("-", 1)[0].lower() == "it" else "en"


def _memory_type(content: str) -> SemanticMemoryType:
    normalized = content.casefold()
    preference_markers = (
        "prefer", "preferred", "favorite", "favourite", "like ",
        "preferisco", "preferita", "preferito", "mi piace",
    )
    if any(marker in normalized for marker in preference_markers):
        return SemanticMemoryType.PREFERENCE
    if any(marker in normalized for marker in (" is ", " are ", " è ", " sono ")):
        return SemanticMemoryType.FACT
    return SemanticMemoryType.NOTE


def parse_memory_intent(text: str, language: str) -> ParsedMemoryIntent | None:
    cleaned = " ".join(text.strip().split())
    language = _lang(language)

    if language == "it":
        supersede = re.fullmatch(
            r"(?:sostituisci|aggiorna)\s+(.+?)\s+con\s+(.+)",
            cleaned,
            re.IGNORECASE,
        )
        if supersede:
            query = supersede.group(1).strip()
            value = supersede.group(2).strip()
            content = f"{query} è {value}"
            return ParsedMemoryIntent(
                operation="SUPERSEDE",
                query=query,
                replacement=content,
                memory_type=_memory_type(content),
            )

        forget = re.fullmatch(
            r"(?:dimentica|scorda|cancella dalla memoria)\s+(.+)",
            cleaned,
            re.IGNORECASE,
        )
        if forget:
            return ParsedMemoryIntent(
                operation="FORGET",
                query=forget.group(1).strip(),
            )

        remember = re.fullmatch(
            r"(?:ricordati(?:\s+che)?|ricorda(?:\s+che)?)\s+(.+)",
            cleaned,
            re.IGNORECASE,
        )
        if remember:
            content = remember.group(1).strip()
            return ParsedMemoryIntent(
                operation="REMEMBER",
                content=content,
                memory_type=_memory_type(content),
            )
    else:
        supersede = re.fullmatch(
            r"(?:replace|update)\s+(.+?)\s+with\s+(.+)",
            cleaned,
            re.IGNORECASE,
        )
        if supersede:
            query = supersede.group(1).strip()
            value = supersede.group(2).strip()
            content = f"{query} is {value}"
            return ParsedMemoryIntent(
                operation="SUPERSEDE",
                query=query,
                replacement=content,
                memory_type=_memory_type(content),
            )

        forget = re.fullmatch(
            r"(?:forget|delete from memory)\s+(.+)",
            cleaned,
            re.IGNORECASE,
        )
        if forget:
            return ParsedMemoryIntent(
                operation="FORGET",
                query=forget.group(1).strip(),
            )

        remember = re.fullmatch(
            r"(?:remember(?:\s+that)?|please remember(?:\s+that)?)\s+(.+)",
            cleaned,
            re.IGNORECASE,
        )
        if remember:
            content = remember.group(1).strip()
            return ParsedMemoryIntent(
                operation="REMEMBER",
                content=content,
                memory_type=_memory_type(content),
            )

    return None


class MemoryManagementSkill:
    name = "memory_management"
    priority = 110

    def matches(self, request: SkillCheckRequest) -> bool:
        pending = request.pending_state or {}
        if pending.get("kind") == "memory_management_clarification":
            return True
        return parse_memory_intent(request.text, request.language) is not None

    def match(self, request: SkillCheckRequest) -> SkillMatch:
        pending = request.pending_state or {}
        if pending.get("kind") == "memory_management_clarification":
            metadata = {
                "operation": "RESOLVE_CLARIFICATION",
            }
        else:
            parsed = parse_memory_intent(request.text, request.language)
            if parsed is None:
                return SkillMatch(matched=False)
            metadata = {
                "operation": parsed.operation,
                "query": parsed.query,
                "content": parsed.content,
                "replacement": parsed.replacement,
                "memory_type": parsed.memory_type.value,
            }

        # Deliberately contains no scope or user identity. Router owns both.
        return SkillMatch(
            matched=True,
            skill_name=self.name,
            token=self.name,
            memory_requirement=MemoryRequirement.NONE,
            metadata=metadata,
        )

    async def execute(
        self,
        request: SkillExecuteRequest,
    ) -> SkillExecuteResponse:
        operation = request.match.metadata.get("operation")
        if not isinstance(operation, str):
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=SkillOutcome.FAILED,
                error=ErrorDetail(code="INVALID_MEMORY_MANAGEMENT_MATCH"),
            )

        payload = {
            "kind": "MEMORY_MANAGEMENT",
            "operation": operation,
        }
        for key in ("query", "content", "replacement", "memory_type"):
            value = request.match.metadata.get(key)
            if value is not None:
                payload[key] = value

        if operation == "RESOLVE_CLARIFICATION":
            payload["selection"] = request.text

        return SkillExecuteResponse(
            correlation=request.correlation,
            outcome=SkillOutcome.HANDLED,
            result={"router_operation": payload},
        )
