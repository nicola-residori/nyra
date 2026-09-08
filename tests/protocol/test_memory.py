from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from shared.protocol.memory import (
    AppliedOperationalEntry,
    MemoryAdmission,
    MemoryPage,
    MemoryRequirement,
    MemoryScope,
    OperationalEntryCreate,
    OperationalEntryType,
    OperationalResolutionRequest,
    OperationalResolutionResult,
    SemanticMemoryCreate,
    SemanticMemorySource,
    SemanticMemoryState,
    SemanticMemoryTombstone,
    SemanticMemoryType,
    SemanticSearchRequest,
    SemanticSearchResult,
    ShortcutValue,
)


def test_memory_enums_have_stable_wire_values():
    assert [item.value for item in MemoryScope] == ["USER", "FAMILY", "SYSTEM"]
    assert [item.value for item in OperationalEntryType] == [
        "ALIAS", "MAPPING", "DEFAULT", "SHORTCUT",
    ]
    assert [item.value for item in SemanticMemoryType] == [
        "FACT", "PREFERENCE", "NOTE", "RELATION",
    ]
    assert [item.value for item in SemanticMemorySource] == [
        "USER_EXPLICIT", "IMPORTED", "SYSTEM",
    ]
    assert [item.value for item in SemanticMemoryState] == [
        "ACTIVE", "SUPERSEDED", "DELETED",
    ]
    assert [item.value for item in MemoryRequirement] == ["NONE", "OPTIONAL", "REQUIRED"]
    assert [item.value for item in MemoryAdmission] == ["NEW", "DUPLICATE", "SUPERSEDES"]


def test_user_scope_requires_an_owner():
    with pytest.raises(ValidationError, match="USER scope requires owner_user_id"):
        OperationalEntryCreate(
            entry_type="ALIAS",
            scope="USER",
            key="desk",
            value={"target": "light.office"},
            idempotency_key="entry-1",
        )


def test_family_and_system_scopes_reject_an_owner():
    for scope in ("FAMILY", "SYSTEM"):
        with pytest.raises(ValidationError, match="must not include owner_user_id"):
            SemanticMemoryCreate(
                memory_type="FACT",
                scope=scope,
                owner_user_id="user-nicola",
                content="The bins go out Tuesday",
                source="USER_EXPLICIT",
                idempotency_key="write-1",
            )


def test_scoped_content_is_trimmed_and_empty_values_are_rejected():
    entry = OperationalEntryCreate(
        entry_type="ALIAS",
        scope="FAMILY",
        key="  Desk Lamp  ",
        value={"target": " light.office "},
        idempotency_key=" create-alias-1 ",
    )
    memory = SemanticMemoryCreate(
        memory_type="PREFERENCE",
        scope="USER",
        owner_user_id=" user-nicola ",
        content="  I prefer espresso  ",
        source="USER_EXPLICIT",
        idempotency_key=" remember-1 ",
    )

    assert entry.key == "Desk Lamp"
    assert entry.idempotency_key == "create-alias-1"
    assert memory.owner_user_id == "user-nicola"
    assert memory.content == "I prefer espresso"

    with pytest.raises(ValidationError):
        SemanticMemoryCreate(
            memory_type="NOTE",
            scope="FAMILY",
            content="   ",
            source="IMPORTED",
            idempotency_key="note-1",
        )


@pytest.mark.parametrize(
    ("entry_type", "value"),
    [
        ("ALIAS", {"target": "light.office"}),
        ("MAPPING", {"source": {"name": "desk"}, "target": {"entity_id": "light.office"}}),
        ("DEFAULT", {"value": {"brightness": 70}}),
        ("SHORTCUT", {"intent": "turn_on", "parameters": {"target": "desk"}}),
    ],
)
def test_operational_values_are_validated_for_their_declared_type(entry_type, value):
    entry = OperationalEntryCreate(
        entry_type=entry_type,
        scope="FAMILY",
        key="desk",
        value=value,
        idempotency_key="entry-1",
    )
    assert entry.entry_type.value == entry_type


def test_shortcut_rejects_execution_and_prompt_fields():
    for forbidden in ("url", "service", "prompt", "code", "loop", "capability"):
        with pytest.raises(ValidationError):
            OperationalEntryCreate(
                entry_type="SHORTCUT",
                scope="FAMILY",
                key="movie time",
                value={"intent": "scene", "parameters": {}, forbidden: "unsafe"},
                idempotency_key=f"shortcut-{forbidden}",
            )


def test_shortcut_parameters_must_be_declarative_json():
    shortcut = ShortcutValue(intent="scene.activate", parameters={"name": "movie", "level": 2})
    assert shortcut.parameters == {"name": "movie", "level": 2}

    with pytest.raises(ValidationError):
        ShortcutValue(intent="scene.activate", parameters={"callback": object()})


def test_resolution_request_normalizes_and_deduplicates_lookup_keys():
    request = OperationalResolutionRequest(
        identity_user_id=" user-nicola ",
        source_id=" nyra-mansarda ",
        area=" mansarda ",
        language=" it-IT ",
        timestamp=datetime(2026, 9, 8, 8, 30, tzinfo=timezone.utc),
        lookup_keys=[" Desk Lamp ", "desk lamp", "TV"],
    )
    assert request.lookup_keys == ["desk lamp", "tv"]
    assert request.identity_user_id == "user-nicola"


def test_resolution_result_exposes_values_and_applied_revisions():
    result = OperationalResolutionResult(
        outcome="SUCCESS",
        values={"desk": {"target": "light.office"}},
        applied=[
            AppliedOperationalEntry(
                entry_id="memop_123e4567-e89b-42d3-a456-426614174000",
                revision=2,
            )
        ],
    )
    assert result.applied[0].revision == 2


def test_semantic_search_requires_an_owner_when_user_scope_is_requested():
    with pytest.raises(ValidationError, match="USER search scope requires owner_user_id"):
        SemanticSearchRequest(query="coffee", scopes=["USER", "FAMILY"])

    request = SemanticSearchRequest(
        query=" coffee ",
        scopes=["USER", "FAMILY", "USER"],
        owner_user_id=" user-nicola ",
        memory_types=["PREFERENCE"],
    )
    assert request.query == "coffee"
    assert request.scopes == [MemoryScope.USER, MemoryScope.FAMILY]


def test_semantic_search_rejects_owner_without_user_scope():
    with pytest.raises(ValidationError, match="owner_user_id requires USER search scope"):
        SemanticSearchRequest(
            query="coffee",
            scopes=["FAMILY", "SYSTEM"],
            owner_user_id="user-nicola",
        )


def test_search_and_page_bounds_are_enforced():
    for limit in (0, 51):
        with pytest.raises(ValidationError):
            SemanticSearchRequest(query="coffee", scopes=["FAMILY"], limit=limit)

    with pytest.raises(ValidationError):
        SemanticSearchRequest(
            query="coffee", scopes=["FAMILY"], minimum_similarity=1.01
        )
    with pytest.raises(ValidationError):
        MemoryPage(limit=101, offset=0)


def test_semantic_results_reject_deleted_items_and_invalid_scores():
    with pytest.raises(ValidationError):
        SemanticSearchResult(
            items=[
                {
                    "memory_id": "mem_123e4567-e89b-42d3-a456-426614174000",
                    "memory_type": "FACT",
                    "scope": "FAMILY",
                    "content": "The bins go out Tuesday",
                    "source": "USER_EXPLICIT",
                    "state": "DELETED",
                    "score": 0.8,
                    "created_at": "2026-09-08T08:30:00Z",
                    "updated_at": "2026-09-08T08:30:00Z",
                    "last_confirmed_at": "2026-09-08T08:30:00Z",
                    "embedding_provider": "test",
                    "embedding_model": "v1",
                }
            ]
        )

    with pytest.raises(ValidationError):
        SemanticSearchResult(items=[], query_model="v1", minimum_similarity=-0.01)


def test_deleted_memory_uses_a_minimal_tombstone_contract():
    tombstone = SemanticMemoryTombstone(
        memory_id="mem_123e4567-e89b-42d3-a456-426614174000",
        deleted_at="2026-09-08T08:30:00Z",
        deletion_trace_id="trc_123e4567-e89b-42d3-a456-426614174001",
    )
    assert tombstone.state is SemanticMemoryState.DELETED
    assert "content" not in SemanticMemoryTombstone.model_fields
    assert "owner_user_id" not in SemanticMemoryTombstone.model_fields

    with pytest.raises(ValidationError):
        SemanticMemoryTombstone(
            memory_id="mem_123e4567-e89b-42d3-a456-426614174000",
            deleted_at="2026-09-08T08:30:00Z",
            deletion_trace_id="trc_123e4567-e89b-42d3-a456-426614174001",
            content="must not survive deletion",
        )


def test_memory_wire_models_forbid_unknown_fields():
    with pytest.raises(ValidationError):
        SemanticSearchRequest(
            query="coffee", scopes=["FAMILY"], authorization="admin"
        )
