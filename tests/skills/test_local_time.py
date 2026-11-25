from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from skills.modules.local_time import LocalTimeSkill


@pytest.mark.parametrize("text", ["Ehi mira, che ore sono?", "Enira. Che ore sono?",
                                  "E in Iran? Che ore sono?", "E in ira che ore sono?", "Che ora è?", "Mi dici l'ora?"])
def test_italian_clock_queries(text):
    assert LocalTimeSkill("Europe/Rome").matches(SimpleNamespace(text=text, language="it-IT"))


@pytest.mark.parametrize("text", ["Ricordami di chiedere che ore sono", "Che ore sono a Tokyo?",
                                  "In Iran che ore sono?", "A che ora è la sveglia?", "Dimmi l'ora e spegni la luce"])
def test_does_not_steal_other_questions(text):
    assert not LocalTimeSkill("Europe/Rome").matches(SimpleNamespace(text=text, language="it"))


def test_uses_household_time_instead_of_server_utc():
    skill = LocalTimeSkill("Europe/Rome")
    with patch("skills.modules.local_time.datetime") as clock:
        clock.now.side_effect = lambda zone: datetime(2026, 11, 25, 0, 5, tzinfo=timezone.utc).astimezone(zone)
        assert skill.execute(None) == "È l’una e 05."
