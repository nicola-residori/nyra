"""Deterministic whole-utterance session closure, never a substring command match."""
import re
import unicodedata

_CLOSING_PHRASES = {"grazie", "chiudi", "ok grazie", "ok", "okay", "thanks", "thank you", "close", "okay thanks", "ok thanks"}


def is_conversation_close(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = " ".join(re.findall(r"\w+", normalized))
    return normalized in _CLOSING_PHRASES
