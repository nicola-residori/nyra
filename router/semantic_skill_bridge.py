import re
from shared.protocol.music import MusicCommand
from shared.protocol.execution_common import NyraOperation, NyraResourceType
from shared.protocol.semantic import SemanticResult


class SemanticSkillBridge:
    def __init__(self, minimum_confidence: float = 0.80):
        self.minimum_confidence = float(minimum_confidence)

    def accept(self, result: SemanticResult, *, text: str | None = None):
        if (
            result.confidence is None
            or result.confidence.score < self.minimum_confidence
        ):
            return None
        if result.music is not None:
            if (
                result.intent != "MUSIC"
                or result.actions
                or result.temporal
                or result.triggers
                or result.conditions
            ):
                return None
            if text is not None:
                utterance = text.casefold().strip()
                if re.match(
                    r"^(parliamo|parlami|raccontami|chi (?:è|sono)|cosa pensi|tell me about|let's talk about)\b",
                    utterance,
                ):
                    return None
                command = result.music.model_dump()
                command["areas"] = [
                    area
                    for area in command["areas"]
                    if re.search(
                        r"(?<!\w)" + re.escape(area.casefold()) + r"(?!\w)", utterance
                    )
                ]
                if command["action"] in ("TRANSFER", "GROUP") and not command["areas"]:
                    return None
                if command["action"] == "TRANSFER" and re.search(
                    r"\b(anche|also)\b|as well", utterance
                ):
                    command["action"] = "GROUP"
                result = result.model_copy(
                    update={"music": MusicCommand.model_validate(command)}
                )
            return result
        if (
            result.temporal is not None
            or result.triggers
            or result.conditions
            or len(result.actions) != 1
        ):
            return None
        a = result.actions[0]
        if a.parameters or a.target is None or not a.target.reference.strip():
            return None
        try:
            NyraOperation(a.operation)
            NyraResourceType(a.target.kind)
        except (TypeError, ValueError):
            return None
        return result
