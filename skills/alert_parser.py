"""Deterministic localized alert parsing. All stored instants are UTC."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ParsedAlert:
    kind: str
    execute_at: datetime
    duration_seconds: float | None
    clock: str | None


_NUMBERS = {
    "un": 1,
    "uno": 1,
    "una": 1,
    "due": 2,
    "tre": 3,
    "quattro": 4,
    "cinque": 5,
    "sei": 6,
    "sette": 7,
    "otto": 8,
    "nove": 9,
    "dieci": 10,
    "quindici": 15,
    "venti": 20,
    "trenta": 30,
    "quaranta": 40,
    "cinquanta": 50,
    "sessanta": 60,
    "a": 1,
    "an": 1,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "fifteen": 15,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
}
_UNITS = {
    "secondo": 1,
    "secondi": 1,
    "second": 1,
    "seconds": 1,
    "minuto": 60,
    "minuti": 60,
    "minute": 60,
    "minutes": 60,
    "ora": 3600,
    "ore": 3600,
    "hour": 3600,
    "hours": 3600,
}
_PREFIXES = (
    (r"(?:svegliami|metti (?:una |la )?sveglia|imposta (?:una |la )?sveglia)", "alarm"),
    (r"chiamami", "call"),
    (r"(?:metti|imposta|avvia) (?:un |il )?timer", "timer"),
    (r"(?:wake me|set (?:an? |the )?alarm)", "alarm"),
    (r"call me", "call"),
    (r"(?:set|start) (?:a |the )?timer", "timer"),
)


def alert_kind(text):
    value = " ".join(text.lower().strip(" .!?").split())
    for prefix, kind in _PREFIXES:
        if re.match(r"^" + prefix + r"(?:\s|$)", value):
            return kind
    return None


def parse_alert(text, language, now, timezone_name):
    if now.tzinfo is None:
        raise ValueError("timezone-aware now required")
    value = " ".join(text.lower().strip(" .!?").split())
    for prefix, kind in _PREFIXES:
        match = re.match(r"^" + prefix + r"\s+(.*)$", value)
        if match:
            break
    else:
        raise ValueError("incomplete alert")
    tail = match.group(1).replace("’", "'")
    tail = (
        tail.replace("un'ora", "un ora")
        .replace("mezz'ora", "30 minuti")
        .replace("mezzora", "30 minuti")
    )
    if tail.startswith(("alle ", "at ")):
        intro, clock_text = tail.split(" ", 1)
        words = re.split(r"\s+e\s+|\s+and\s+", clock_text)
        if len(words) <= 2:
            normalized = []
            for word in words:
                word = word.strip()
                normalized.append(str(_NUMBERS[word]) if word in _NUMBERS else word)
            tail = intro + " " + ":".join(normalized)
    relative = re.fullmatch(r"(?:tra|fra|di|in|for)\s+(.+)", tail)
    if relative:
        parts = re.split(r"\s+(?:e|and)\s+|\s*,\s+(?=\w+\s+\w)", relative.group(1))
        seconds = 0.0
        for part in parts:
            unit_match = re.fullmatch(r"([\w.,]+)\s+(\w+)", part)
            if not unit_match:
                raise ValueError("invalid duration")
            amount, unit = unit_match.groups()
            try:
                amount = (
                    float(_NUMBERS[amount])
                    if amount in _NUMBERS
                    else float(amount.replace(",", "."))
                )
            except ValueError:
                raise ValueError("invalid duration") from None
            if unit not in _UNITS or not math.isfinite(amount) or amount <= 0:
                raise ValueError("invalid duration")
            seconds += amount * _UNITS[unit]
        if seconds > 366 * 86400:
            raise ValueError("duration exceeds one year")
        return ParsedAlert(
            kind,
            now.astimezone(timezone.utc) + timedelta(seconds=seconds),
            seconds,
            None,
        )
    absolute = re.fullmatch(r"(?:alle|at)\s+(\d{1,2})(?:[:.](\d{2}))?", tail)
    if not absolute or kind == "timer":
        raise ValueError("invalid clock")
    hour, minute = int(absolute.group(1)), int(absolute.group(2) or 0)
    if hour > 23 or minute > 59:
        raise ValueError("invalid clock")
    zone = ZoneInfo(timezone_name)
    local = now.astimezone(zone)
    naive = local.replace(
        hour=hour, minute=minute, second=0, microsecond=0, tzinfo=None
    )
    if naive <= local.replace(tzinfo=None):
        naive += timedelta(days=1)
    candidates = set()
    for fold in (0, 1):
        utc = naive.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if utc.astimezone(zone).replace(tzinfo=None) == naive:
            candidates.add(utc)
    if len(candidates) != 1:
        raise ValueError("DST clock is nonexistent or ambiguous")
    return ParsedAlert(kind, candidates.pop(), None, f"{hour:02d}:{minute:02d}")


def call_message(alert, language, name=None):
    it = language.lower().startswith("it")
    if alert.duration_seconds is None:
        sentence = f"Sono le {alert.clock}." if it else f"It is {alert.clock}."
    else:
        seconds = alert.duration_seconds
        unit = "second"
        amount = seconds
        if seconds % 3600 == 0:
            unit, amount = "hour", seconds / 3600
        elif seconds % 60 == 0:
            unit, amount = "minute", seconds / 60
        n = format(amount, "g")
        if it:
            units = {
                "second": ("secondo", "secondi"),
                "minute": ("minuto", "minuti"),
                "hour": ("ora", "ore"),
            }
            word = units[unit][amount != 1]
            sentence = (
                f'{"È passata" if unit=="hour" else "È passato"} {n} {word}.'
                if amount == 1
                else f'Sono passat{"e" if unit=="hour" else "i"} {n} {word}.'
            )
        else:
            sentence = f'{n} {unit}{"" if amount==1 else "s"} {"has" if amount==1 else "have"} passed.'
    return f"{name}, {sentence[0].lower()}{sentence[1:]}" if name else sentence
