from datetime import datetime, timedelta, timezone

import pytest

from memory.operational import OperationalContextService, OperationalEntryNotFound
from memory.storage import MemoryStore
from shared.protocol.memory import OperationalEntryCreate, OperationalEntryUpdate


NOW = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def service(tmp_path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    store.initialize()
    ticks = iter((NOW + timedelta(seconds=index) for index in range(20)))
    return OperationalContextService(store, clock=lambda: next(ticks))


def alias(key, target, *, scope="FAMILY", owner=None, enabled=True, idem="entry-1"):
    return OperationalEntryCreate(
        entry_type="ALIAS",
        scope=scope,
        owner_user_id=owner,
        key=key,
        value={"target": target},
        enabled=enabled,
        idempotency_key=idem,
    )


def test_create_and_get_preserve_typed_operational_entry(service):
    created = service.create(alias("Desk", "light.office"))

    loaded = service.get(created.entry_id)

    assert loaded == created
    assert created.entry_id.startswith("memop_")
    assert created.revision == 1
    assert created.key == "Desk"
    assert created.value.target == "light.office"
    assert created.created_at == NOW
    assert created.updated_at == NOW


def test_update_increments_revision_and_preserves_creation_time(service):
    created = service.create(alias("Desk", "light.office"))
    updated = service.update(
        created.entry_id,
        OperationalEntryUpdate(
            entry_type="ALIAS",
            scope="FAMILY",
            key="Desk",
            value={"target": "light.study"},
            enabled=False,
            idempotency_key="entry-2",
        ),
    )

    assert updated.revision == 2
    assert updated.created_at == created.created_at
    assert updated.updated_at == NOW + timedelta(seconds=1)
    assert updated.value.target == "light.study"
    assert updated.enabled is False


def test_delete_removes_entry_and_missing_ids_are_distinct(service):
    created = service.create(alias("Desk", "light.office"))
    service.delete(created.entry_id)

    with pytest.raises(OperationalEntryNotFound):
        service.get(created.entry_id)
    with pytest.raises(OperationalEntryNotFound):
        service.delete(created.entry_id)


def test_list_filters_type_scope_owner_and_enabled_state(service):
    service.create(alias("Family", "light.family", idem="1"))
    service.create(alias("Disabled", "light.disabled", enabled=False, idem="2"))
    service.create(alias("Nicola", "light.nicola", scope="USER", owner="user-nicola", idem="3"))
    service.create(alias("Other", "light.other", scope="USER", owner="user-other", idem="4"))

    items = service.list_entries(
        entry_type="ALIAS", scope="USER", owner_user_id="user-nicola", enabled=True
    )

    assert [item.key for item in items] == ["Nicola"]


def test_store_reopens_with_persisted_records(tmp_path):
    path = tmp_path / "memory.sqlite3"
    first = OperationalContextService(MemoryStore(path), clock=lambda: NOW)
    first.store.initialize()
    created = first.create(alias("Desk", "light.office"))

    second_store = MemoryStore(path)
    second_store.initialize()
    second = OperationalContextService(second_store, clock=lambda: NOW)

    assert second.get(created.entry_id).value.target == "light.office"

