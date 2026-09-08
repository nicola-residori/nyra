from __future__ import annotations

import unicodedata
from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from .common import CommonOutcome
from .ids import validate_prefixed_uuid


def _required_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        raise ValueError("value must not be empty")
    return normalized


class MemoryScope(StrEnum):
    USER = "USER"
    FAMILY = "FAMILY"
    SYSTEM = "SYSTEM"


class OperationalEntryType(StrEnum):
    ALIAS = "ALIAS"
    MAPPING = "MAPPING"
    DEFAULT = "DEFAULT"
    SHORTCUT = "SHORTCUT"


class SemanticMemoryType(StrEnum):
    FACT = "FACT"
    PREFERENCE = "PREFERENCE"
    NOTE = "NOTE"
    RELATION = "RELATION"


class SemanticMemorySource(StrEnum):
    USER_EXPLICIT = "USER_EXPLICIT"
    IMPORTED = "IMPORTED"
    SYSTEM = "SYSTEM"


class SemanticMemoryState(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    DELETED = "DELETED"


class MemoryRequirement(StrEnum):
    NONE = "NONE"
    OPTIONAL = "OPTIONAL"
    REQUIRED = "REQUIRED"


class MemoryAdmission(StrEnum):
    NEW = "NEW"
    DUPLICATE = "DUPLICATE"
    SUPERSEDES = "SUPERSEDES"


class MemoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScopedModel(MemoryModel):
    scope: MemoryScope
    owner_user_id: str | None = Field(default=None, max_length=255)

    @field_validator("owner_user_id")
    @classmethod
    def normalize_owner(cls, value: str | None) -> str | None:
        return _required_text(value) if value is not None else None

    @model_validator(mode="after")
    def validate_owner_for_scope(self):
        if self.scope is MemoryScope.USER and self.owner_user_id is None:
            raise ValueError("USER scope requires owner_user_id")
        if self.scope is not MemoryScope.USER and self.owner_user_id is not None:
            raise ValueError("FAMILY and SYSTEM scopes must not include owner_user_id")
        return self


class AliasValue(MemoryModel):
    target: str = Field(min_length=1, max_length=512)

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return _required_text(value)


class MappingValue(MemoryModel):
    source: JsonValue
    target: JsonValue


class DefaultValue(MemoryModel):
    value: JsonValue


class ShortcutValue(MemoryModel):
    intent: str = Field(min_length=1, max_length=255)
    parameters: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("intent")
    @classmethod
    def normalize_intent(cls, value: str) -> str:
        return _required_text(value)


OperationalValue = AliasValue | MappingValue | DefaultValue | ShortcutValue


class OperationalEntryCreate(ScopedModel):
    entry_type: OperationalEntryType
    key: str = Field(min_length=1, max_length=255)
    value: OperationalValue
    enabled: bool = True
    idempotency_key: str = Field(min_length=1, max_length=255)

    @field_validator("key", "idempotency_key")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return _required_text(value)

    @model_validator(mode="after")
    def validate_value_type(self):
        expected = {
            OperationalEntryType.ALIAS: AliasValue,
            OperationalEntryType.MAPPING: MappingValue,
            OperationalEntryType.DEFAULT: DefaultValue,
            OperationalEntryType.SHORTCUT: ShortcutValue,
        }[self.entry_type]
        if not isinstance(self.value, expected):
            raise ValueError(f"{self.entry_type.value} requires {expected.__name__}")
        return self


class OperationalEntryUpdate(OperationalEntryCreate):
    pass


class OperationalEntry(ScopedModel):
    entry_id: str
    entry_type: OperationalEntryType
    key: str
    value: OperationalValue
    enabled: bool
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime

    @field_validator("entry_id")
    @classmethod
    def validate_entry_id(cls, value: str) -> str:
        return validate_prefixed_uuid(value, "memop")


class OperationalResolutionRequest(MemoryModel):
    identity_user_id: str | None = Field(default=None, max_length=255)
    source_id: str | None = Field(default=None, max_length=255)
    area: str | None = Field(default=None, max_length=255)
    language: str = Field(min_length=2, max_length=35)
    timestamp: datetime
    lookup_keys: list[str] = Field(min_length=1, max_length=100)

    @field_validator("identity_user_id", "source_id", "area")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        return _required_text(value) if value is not None else None

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        return _required_text(value)

    @field_validator("lookup_keys")
    @classmethod
    def normalize_lookup_keys(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = unicodedata.normalize("NFKC", value).strip().casefold()
            if not key:
                raise ValueError("lookup key must not be empty")
            if key not in seen:
                normalized.append(key)
                seen.add(key)
        return normalized


class AppliedOperationalEntry(MemoryModel):
    entry_id: str
    revision: int = Field(ge=1)

    @field_validator("entry_id")
    @classmethod
    def validate_entry_id(cls, value: str) -> str:
        return validate_prefixed_uuid(value, "memop")


class OperationalConflict(MemoryModel):
    key: str
    scope: MemoryScope
    entry_ids: list[str] = Field(min_length=2)


class OperationalResolutionResult(MemoryModel):
    outcome: CommonOutcome
    values: dict[str, JsonValue] = Field(default_factory=dict)
    applied: list[AppliedOperationalEntry] = Field(default_factory=list)
    conflicts: list[OperationalConflict] = Field(default_factory=list)


class SemanticMemoryCreate(ScopedModel):
    memory_type: SemanticMemoryType
    content: str = Field(min_length=1, max_length=10_000)
    source: SemanticMemorySource
    idempotency_key: str = Field(min_length=1, max_length=255)

    @field_validator("content", "idempotency_key")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return _required_text(value)


class SemanticMemoryConfirm(MemoryModel):
    idempotency_key: str = Field(min_length=1, max_length=255)

    @field_validator("idempotency_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return _required_text(value)


class SemanticMemorySupersede(MemoryModel):
    replacement: SemanticMemoryCreate
    idempotency_key: str = Field(min_length=1, max_length=255)

    @field_validator("idempotency_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return _required_text(value)


class SemanticMemoryDelete(MemoryModel):
    idempotency_key: str = Field(min_length=1, max_length=255)

    @field_validator("idempotency_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return _required_text(value)


class SemanticMemory(ScopedModel):
    memory_id: str
    memory_type: SemanticMemoryType
    content: str | None = None
    source: SemanticMemorySource | None = None
    state: Literal[
        SemanticMemoryState.ACTIVE,
        SemanticMemoryState.SUPERSEDED,
    ]
    supersedes_memory_id: str | None = None
    superseded_by_memory_id: str | None = None
    created_at: datetime
    updated_at: datetime
    last_confirmed_at: datetime
    deleted_at: datetime | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None

    @field_validator("memory_id", "supersedes_memory_id", "superseded_by_memory_id")
    @classmethod
    def validate_memory_ids(cls, value: str | None) -> str | None:
        return validate_prefixed_uuid(value, "mem") if value is not None else None


class SemanticMemoryTombstone(MemoryModel):
    memory_id: str
    state: Literal[SemanticMemoryState.DELETED] = SemanticMemoryState.DELETED
    deleted_at: datetime
    deletion_trace_id: str

    @field_validator("memory_id")
    @classmethod
    def validate_memory_id(cls, value: str) -> str:
        return validate_prefixed_uuid(value, "mem")

    @field_validator("deletion_trace_id")
    @classmethod
    def validate_trace_id(cls, value: str) -> str:
        return validate_prefixed_uuid(value, "trc")


class SemanticSearchRequest(MemoryModel):
    query: str = Field(min_length=1, max_length=10_000)
    scopes: list[MemoryScope] = Field(min_length=1, max_length=3)
    owner_user_id: str | None = Field(default=None, max_length=255)
    memory_types: list[SemanticMemoryType] = Field(default_factory=list, max_length=4)
    limit: int = Field(default=10, ge=1, le=50)
    minimum_similarity: float = Field(default=0.35, ge=0.0, le=1.0)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return _required_text(value)

    @field_validator("owner_user_id")
    @classmethod
    def normalize_owner(cls, value: str | None) -> str | None:
        return _required_text(value) if value is not None else None

    @field_validator("scopes")
    @classmethod
    def deduplicate_scopes(cls, scopes: list[MemoryScope]) -> list[MemoryScope]:
        return list(dict.fromkeys(scopes))

    @field_validator("memory_types")
    @classmethod
    def deduplicate_types(cls, types: list[SemanticMemoryType]) -> list[SemanticMemoryType]:
        return list(dict.fromkeys(types))

    @model_validator(mode="after")
    def validate_search_owner(self):
        includes_user = MemoryScope.USER in self.scopes
        if includes_user and self.owner_user_id is None:
            raise ValueError("USER search scope requires owner_user_id")
        if not includes_user and self.owner_user_id is not None:
            raise ValueError("owner_user_id requires USER search scope")
        return self


class SemanticSearchItem(SemanticMemory):
    state: Literal[SemanticMemoryState.ACTIVE] = SemanticMemoryState.ACTIVE
    content: str
    source: SemanticMemorySource
    score: float = Field(ge=0.0, le=1.0)
    embedding_provider: str
    embedding_model: str


class SemanticSearchResult(MemoryModel):
    items: list[SemanticSearchItem] = Field(default_factory=list)
    query_model: str | None = None
    minimum_similarity: float = Field(default=0.35, ge=0.0, le=1.0)


class MemoryPage(MemoryModel):
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class MemoryMutationResult(MemoryModel):
    outcome: CommonOutcome
    admission: MemoryAdmission | None = None
    memory_id: str | None = None
    entry_id: str | None = None
    revision: int | None = Field(default=None, ge=1)

    @field_validator("memory_id")
    @classmethod
    def validate_memory_id(cls, value: str | None) -> str | None:
        return validate_prefixed_uuid(value, "mem") if value is not None else None

    @field_validator("entry_id")
    @classmethod
    def validate_entry_id(cls, value: str | None) -> str | None:
        return validate_prefixed_uuid(value, "memop") if value is not None else None
