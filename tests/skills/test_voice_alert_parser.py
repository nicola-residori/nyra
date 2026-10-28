from datetime import datetime, timezone
import pytest
from skills.alert_parser import parse_alert, call_message

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "text,lang,kind,seconds",
    [
        ("svegliami tra 10 minuti", "it-IT", "alarm", 600),
        ("metti una sveglia tra un minuto", "it", "alarm", 60),
        ("chiamami tra due ore", "it", "call", 7200),
        ("metti un timer di 1 minuto e 30 secondi", "it", "timer", 90),
        ("set a timer for 30 seconds", "en-US", "timer", 30),
        ("wake me in 2 hours", "en", "alarm", 7200),
        ("call me in ten minutes", "en", "call", 600),
    ],
)
def test_relative_commands_preserve_kind_and_duration(text, lang, kind, seconds):
    result = parse_alert(text, lang, NOW, "Europe/Rome")
    assert result.kind == kind
    assert result.duration_seconds == seconds
    assert (result.execute_at - NOW).total_seconds() == seconds


@pytest.mark.parametrize(
    "text,lang,utc",
    [
        ("svegliami alle 14:30", "it", "2026-10-28T13:30:00+00:00"),
        ("chiamami alle 7", "it", "2026-10-29T06:00:00+00:00"),
        ("set an alarm at 14:30", "en", "2026-10-28T13:30:00+00:00"),
    ],
)
def test_absolute_clock_uses_installation_zone_and_next_day(text, lang, utc):
    assert parse_alert(text, lang, NOW, "Europe/Rome").execute_at.isoformat() == utc


@pytest.mark.parametrize(
    "text",
    [
        "metti un timer di 0 secondi",
        "svegliami tra -1 minuti",
        "metti un timer di nan ore",
        "svegliami alle 25:00",
        "metti una sveglia",
    ],
)
def test_invalid_or_incomplete_alert_clarifies(text):
    with pytest.raises(ValueError):
        parse_alert(text, "it", NOW, "Europe/Rome")


@pytest.mark.parametrize(
    "now", ["2026-03-28T23:00:00+00:00", "2026-10-24T23:00:00+00:00"]
)
def test_dst_gap_and_fold_are_not_silently_guessed(now):
    with pytest.raises(ValueError, match="DST"):
        parse_alert(
            "svegliami alle 2:30", "it", datetime.fromisoformat(now), "Europe/Rome"
        )


def test_call_phrases_distinguish_duration_and_clock_and_language():
    relative = parse_alert("chiamami tra 10 minuti", "it", NOW, "Europe/Rome")
    assert call_message(relative, "it", "Nicola") == "Nicola, sono passati 10 minuti."
    absolute = parse_alert("call me at 14:30", "en", NOW, "Europe/Rome")
    assert call_message(absolute, "en", None) == "It is 14:30."


@pytest.mark.parametrize(
    "text,seconds",
    [
        ("svegliami tra un'ora", 3600),
        ("metti un timer di mezzora", 1800),
        ("chiamami tra dieci minuti", 600),
    ],
)
def test_spoken_italian_duration_forms(text, seconds):
    assert parse_alert(text, "it", NOW, "Europe/Rome").duration_seconds == seconds


@pytest.mark.parametrize(
    "text,clock",
    [("svegliami alle sette e trenta", "07:30"), ("chiamami alle quindici", "15:00")],
)
def test_spoken_italian_clock_forms(text, clock):
    assert parse_alert(text, "it", NOW, "Europe/Rome").clock == clock
