from datetime import datetime, timezone

import pytest

from memory.operational import OperationalContextService
from memory.storage import MemoryStore
from shared.protocol.common import CommonOutcome
from shared.protocol.memory import OperationalEntryCreate, OperationalResolutionRequest


NOW = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def service(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    return OperationalContextService(store, clock=lambda: NOW)


def create(service, entry_type, key, value, *, scope="FAMILY", owner=None, enabled=True, idem=None):
    return service.create(
        OperationalEntryCreate(
            entry_type=entry_type,
            scope=scope,
            owner_user_id=owner,
            key=key,
            value=value,
            enabled=enabled,
            idempotency_key=idem or f"{entry_type}-{scope}-{owner}-{key}-{value}",
        )
    )


def request(*lookups, user=None):
    return OperationalResolutionRequest(
        identity_user_id=user,
        source_id="nyra-mansarda",
        area="mansarda",
        language="it-IT",
        timestamp=NOW,
        lookups=[{"entry_type": entry_type, "key": key} for entry_type, key in lookups],
    )


def test_user_entry_wins_over_family_and_system(service):
    create(service, "ALIAS", "desk", {"target": "light.system"}, scope="SYSTEM")
    create(service, "ALIAS", "desk", {"target": "light.family"}, scope="FAMILY")
    user = create(
        service, "ALIAS", "desk", {"target": "light.nicola"},
        scope="USER", owner="user-nicola",
    )

    result = service.resolve(request(("ALIAS", "desk"), user="user-nicola"))

    assert result.outcome is CommonOutcome.SUCCESS
    assert result.values == {"ALIAS": {"desk": {"target": "light.nicola"}}}
    assert [(item.entry_id, item.revision) for item in result.applied] == [
        (user.entry_id, 1)
    ]


def test_guest_and_other_user_records_are_never_candidates(service):
    family = create(service, "ALIAS", "desk", {"target": "light.family"})
    create(
        service, "ALIAS", "desk", {"target": "light.nicola"},
        scope="USER", owner="user-nicola",
    )

    guest = service.resolve(request(("ALIAS", "desk")))
    other = service.resolve(request(("ALIAS", "desk"), user="user-other"))

    assert guest.applied[0].entry_id == family.entry_id
    assert other.applied[0].entry_id == family.entry_id


def test_same_scope_incompatible_values_are_ambiguous(service):
    first = create(service, "ALIAS", "desk", {"target": "light.one"}, idem="one")
    second = create(service, "ALIAS", "desk", {"target": "light.two"}, idem="two")

    result = service.resolve(request(("ALIAS", "desk")))

    assert result.outcome is CommonOutcome.AMBIGUOUS
    assert result.values == {}
    assert result.applied == []
    assert result.conflicts[0].entry_type.value == "ALIAS"
    assert result.conflicts[0].key == "desk"
    assert set(result.conflicts[0].entry_ids) == {first.entry_id, second.entry_id}


def test_identical_same_scope_values_do_not_create_false_ambiguity(service):
    first = create(service, "ALIAS", "desk", {"target": "light.one"}, idem="one")
    create(service, "ALIAS", "desk", {"target": "light.one"}, idem="two")

    result = service.resolve(request(("ALIAS", "desk")))

    assert result.outcome is CommonOutcome.SUCCESS
    assert result.applied[0].entry_id == first.entry_id


def test_disabled_higher_scope_does_not_hide_enabled_lower_scope(service):
    family = create(service, "ALIAS", "desk", {"target": "light.family"})
    create(
        service, "ALIAS", "desk", {"target": "light.nicola"},
        scope="USER", owner="user-nicola", enabled=False,
    )

    result = service.resolve(request(("ALIAS", "desk"), user="user-nicola"))

    assert result.applied[0].entry_id == family.entry_id


def test_same_key_can_resolve_independently_for_different_types(service):
    create(service, "ALIAS", "desk", {"target": "light.office"})
    create(service, "DEFAULT", "desk", {"value": {"brightness": 70}})

    result = service.resolve(
        request(("ALIAS", "desk"), ("DEFAULT", "desk"))
    )

    assert result.values == {
        "ALIAS": {"desk": {"target": "light.office"}},
        "DEFAULT": {"desk": {"value": {"brightness": 70}}},
    }


def test_missing_lookup_returns_success_with_no_values(service):
    result = service.resolve(request(("ALIAS", "missing")))

    assert result.outcome is CommonOutcome.SUCCESS
    assert result.values == {}
    assert result.applied == []


def test_unicode_case_and_whitespace_keys_resolve_canonically(service):
    created = create(service, "ALIAS", "  Caffè  ", {"target": "switch.coffee"})

    result = service.resolve(request(("ALIAS", "CAFFE\u0300")))

    assert result.applied[0].entry_id == created.entry_id
