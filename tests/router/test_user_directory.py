from datetime import datetime, timezone

import pytest

from router.user_directory import UserDirectory


class Clock:
    def __init__(self):
        self.now = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def test_user_directory_persists_and_updates_a_trusted_name(tmp_path):
    clock = Clock()
    database = tmp_path / "router.db"
    directory = UserDirectory(database, clock=clock)
    directory.initialize()

    first = directory.upsert("home_assistant", "ha-1", "Nicola")
    clock.now = datetime(2026, 9, 8, 11, 0, tzinfo=timezone.utc)
    second = directory.upsert("home_assistant", "ha-1", "Nicola Residori")

    reopened = UserDirectory(database)
    reopened.initialize()
    assert first.user_id == "ha-1"
    assert first.updated_at.isoformat() == "2026-09-08T10:00:00+00:00"
    assert second.display_name == "Nicola Residori"
    assert reopened.get("home_assistant", "ha-1").display_name == "Nicola Residori"


def test_empty_name_cannot_erase_a_known_reference(tmp_path):
    directory = UserDirectory(tmp_path / "router.db")
    directory.initialize()
    directory.upsert("home_assistant", "ha-1", "Nicola")

    with pytest.raises(ValueError, match="display_name is required"):
        directory.upsert("home_assistant", "ha-1", "   ")

    assert directory.get("home_assistant", "ha-1").display_name == "Nicola"


def test_user_directory_separates_identity_providers_and_initializes_twice(tmp_path):
    directory = UserDirectory(tmp_path / "router.db")
    directory.initialize()
    directory.initialize()
    directory.upsert("home_assistant", "same-id", "Nicola")
    directory.upsert("example_provider", "same-id", "Alice")

    assert directory.get("home_assistant", "same-id").display_name == "Nicola"
    assert directory.get("example_provider", "same-id").display_name == "Alice"
    assert directory.get("home_assistant", "missing") is None
