"""Validated musical intent and bounded catalog clarifications."""

import re
import time
from shared.protocol.music import MusicCommand
from shared.protocol.skills import SkillMatch, SkillExecuteResponse, SkillOutcome

ORDINALS = {
    "il primo": 0,
    "la prima": 0,
    "primo": 0,
    "prima": 0,
    "1": 0,
    "il secondo": 1,
    "la seconda": 1,
    "secondo": 1,
    "seconda": 1,
    "2": 1,
    "il terzo": 2,
    "la terza": 2,
    "3": 2,
    "the first": 0,
    "the second": 1,
    "the third": 2,
}


def looks_like_music(text):
    return bool(
        re.search(
            r"^(?:fammi ascoltare|riproduci|ascoltiamo|metti|pausa|riprendi|prossimo brano|cambia (?:pezzo|brano))\b",
            text.strip().lower(),
        )
    )


class MusicSkill:
    name = "music"
    priority = 117

    def __init__(self, capability, *, clock=time.time):
        self.capability = capability
        self.clock = clock

    def matches(self, request):
        return bool(
            (request.semantic and request.semantic.music)
            or (
                (request.pending_state or {}).get("kind") == "music"
                and request.text.strip(" .!?").lower() in ORDINALS
            )
        )

    def match(self, request):
        return SkillMatch(
            matched=True,
            skill_name=self.name,
            token=self.name,
            metadata=(
                {"command": request.semantic.music.model_dump(mode="json")}
                if request.semantic and request.semantic.music
                else {}
            ),
        )

    async def execute(self, request):
        it = request.language.lower().startswith("it")

        def reply(text, clarify=False, pending=None):
            return SkillExecuteResponse(
                correlation=request.correlation,
                outcome=(
                    SkillOutcome.NEEDS_CLARIFICATION
                    if clarify
                    else SkillOutcome.HANDLED
                ),
                text=text,
                pending_state=pending,
            )

        source = request.context.get("source_id")
        if not source:
            return reply("Da quale speaker?" if it else "Which speaker?", True)
        payload = {
            "source_id": source,
            "session_id": request.context.get("session_id")
            or request.correlation.origin_request_id,
            "language": request.language,
            "correlation": request.correlation.model_dump(mode="json"),
        }
        command = request.match.metadata.get("command")
        pending_room = request.pending_state or {}
        if (
            command
            and pending_room.get("kind") == "music_room"
            and not looks_like_music(request.text)
        ):
            if (pending_room.get("source_id"), pending_room.get("session_id")) != (
                source,
                payload["session_id"],
            ) or self.clock() > pending_room.get("expires_at", 0):
                return reply(
                    "La richiesta musicale è scaduta: ripetila."
                    if it
                    else "The music request expired; repeat it."
                )
            original = pending_room["command"]
            if command.get("action") == original.get("action") and command.get(
                "query"
            ) == original.get("query"):
                command = {**original, "areas": command.get("areas", [])}
        if command:
            payload["command"] = MusicCommand.model_validate(command).model_dump(
                mode="json"
            )
        else:
            choices = (request.pending_state or {}).get("choices", [])
            index = ORDINALS.get(request.text.strip(" .!?").lower(), -1)
            if not 0 <= index < len(choices):
                return reply(
                    "Quale risultato intendi?" if it else "Which result?",
                    True,
                    request.pending_state,
                )
            payload["selection"] = choices[index]["token"]
        try:
            result = await self.capability.music(payload)
        except Exception:
            return reply(
                "Il servizio musicale non è disponibile."
                if it
                else "The music service is unavailable."
            )
        pending = result.get("pending") or (
            {"kind": "music", "choices": result["choices"]}
            if result.get("choices")
            else None
        )
        return reply(
            result.get("text")
            or (
                "Non posso completare la richiesta musicale."
                if it
                else "I cannot complete the music request."
            ),
            result.get("status") == "CLARIFY",
            pending,
        )
