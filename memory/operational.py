from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone
from uuid import uuid4

from memory.storage import MemoryStore
from shared.protocol.common import CommonOutcome
from shared.protocol.memory import (
    AppliedOperationalEntry,
    MemoryScope,
    OperationalConflict,
    OperationalEntry,
    OperationalEntryCreate,
    OperationalEntryType,
    OperationalEntryUpdate,
    OperationalResolutionRequest,
    OperationalResolutionResult,
)


class OperationalEntryNotFound(LookupError):
    pass


def normalize_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip().casefold()


class OperationalContextService:
    def __init__(self, store: MemoryStore, *, clock=None, id_factory=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.id_factory = id_factory or (lambda: f"memop_{uuid4()}")

    @staticmethod
    def _row_to_entry(row) -> OperationalEntry:
        return OperationalEntry(
            entry_id=row["entry_id"],
            entry_type=row["entry_type"],
            scope=row["scope"],
            owner_user_id=row["owner_user_id"],
            key=row["key"],
            value=json.loads(row["value_json"]),
            enabled=bool(row["enabled"]),
            revision=row["revision"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create(self, command: OperationalEntryCreate) -> OperationalEntry:
        entry_id = self.id_factory()
        now = self.clock().isoformat()
        with self.store.connect() as connection:
            connection.execute(
                """
                INSERT INTO operational_entries (
                    entry_id, entry_type, scope, owner_user_id, key,
                    normalized_key, value_json, enabled, revision,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    entry_id,
                    command.entry_type.value,
                    command.scope.value,
                    command.owner_user_id,
                    command.key,
                    normalize_key(command.key),
                    json.dumps(command.value.model_dump(mode="json"), sort_keys=True),
                    int(command.enabled),
                    now,
                    now,
                ),
            )
        return self.get(entry_id)

    def get(self, entry_id: str) -> OperationalEntry:
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT * FROM operational_entries WHERE entry_id = ?", (entry_id,)
            ).fetchone()
        if row is None:
            raise OperationalEntryNotFound(entry_id)
        return self._row_to_entry(row)

    def update(
        self, entry_id: str, command: OperationalEntryUpdate
    ) -> OperationalEntry:
        current = self.get(entry_id)
        now = self.clock().isoformat()
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE operational_entries
                SET entry_type = ?, scope = ?, owner_user_id = ?, key = ?,
                    normalized_key = ?, value_json = ?, enabled = ?,
                    revision = revision + 1, updated_at = ?
                WHERE entry_id = ? AND revision = ?
                """,
                (
                    command.entry_type.value,
                    command.scope.value,
                    command.owner_user_id,
                    command.key,
                    normalize_key(command.key),
                    json.dumps(command.value.model_dump(mode="json"), sort_keys=True),
                    int(command.enabled),
                    now,
                    entry_id,
                    current.revision,
                ),
            )
            if cursor.rowcount != 1:
                raise OperationalEntryNotFound(entry_id)
        return self.get(entry_id)

    def delete(self, entry_id: str) -> None:
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "DELETE FROM operational_entries WHERE entry_id = ?", (entry_id,)
            )
            if cursor.rowcount != 1:
                raise OperationalEntryNotFound(entry_id)

    def list_entries(
        self,
        *,
        entry_type: OperationalEntryType | str | None = None,
        scope: MemoryScope | str | None = None,
        owner_user_id: str | None = None,
        enabled: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[OperationalEntry]:
        clauses: list[str] = []
        args: list[object] = []
        if entry_type is not None:
            clauses.append("entry_type = ?")
            args.append(OperationalEntryType(entry_type).value)
        if scope is not None:
            clauses.append("scope = ?")
            args.append(MemoryScope(scope).value)
        if owner_user_id is not None:
            clauses.append("owner_user_id = ?")
            args.append(owner_user_id)
        if enabled is not None:
            clauses.append("enabled = ?")
            args.append(int(enabled))
        query = "SELECT * FROM operational_entries"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at, rowid LIMIT ? OFFSET ?"
        args.extend((limit, offset))
        with self.store.connect() as connection:
            rows = connection.execute(query, args).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def resolve(
        self, request: OperationalResolutionRequest
    ) -> OperationalResolutionResult:
        resolved: dict[str, dict[str, object]] = {}
        applied: list[AppliedOperationalEntry] = []
        conflicts: list[OperationalConflict] = []
        precedence = (MemoryScope.USER, MemoryScope.FAMILY, MemoryScope.SYSTEM)

        with self.store.connect() as connection:
            for lookup in request.lookups:
                scope_clause = "scope IN ('FAMILY', 'SYSTEM')"
                args: list[object] = [lookup.entry_type.value, lookup.key]
                if request.identity_user_id is not None:
                    scope_clause = (
                        "(scope IN ('FAMILY', 'SYSTEM') OR "
                        "(scope = 'USER' AND owner_user_id = ?))"
                    )
                    args.append(request.identity_user_id)
                rows = connection.execute(
                    f"""
                    SELECT * FROM operational_entries
                    WHERE entry_type = ? AND normalized_key = ? AND enabled = 1
                      AND {scope_clause}
                    ORDER BY created_at, rowid
                    """,
                    args,
                ).fetchall()
                entries = [self._row_to_entry(row) for row in rows]

                candidates: list[OperationalEntry] = []
                for scope in precedence:
                    candidates = [entry for entry in entries if entry.scope is scope]
                    if candidates:
                        break
                if not candidates:
                    continue

                distinct_values = {
                    json.dumps(
                        entry.value.model_dump(mode="json"), sort_keys=True
                    )
                    for entry in candidates
                }
                if len(distinct_values) > 1:
                    conflicts.append(
                        OperationalConflict(
                            entry_type=lookup.entry_type,
                            key=lookup.key,
                            scope=candidates[0].scope,
                            entry_ids=[entry.entry_id for entry in candidates],
                        )
                    )
                    continue

                chosen = candidates[0]
                resolved.setdefault(lookup.entry_type.value, {})[lookup.key] = (
                    chosen.value.model_dump(mode="json")
                )
                applied.append(
                    AppliedOperationalEntry(
                        entry_id=chosen.entry_id, revision=chosen.revision
                    )
                )

        return OperationalResolutionResult(
            outcome=(CommonOutcome.AMBIGUOUS if conflicts else CommonOutcome.SUCCESS),
            values=resolved,
            applied=applied,
            conflicts=conflicts,
        )
