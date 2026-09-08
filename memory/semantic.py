from __future__ import annotations

import hashlib
import json
import unicodedata
from array import array
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from memory.embeddings import EmbeddingProvider, EmbeddingVector
from memory.operational import (
    IdempotencyConflict,
    IdempotentResult,
    OperationalContextService,
)
from memory.storage import MemoryStore
from shared.protocol.memory import (
    MemoryAdmission,
    MemoryScope,
    SemanticMemory,
    SemanticMemoryCreate,
    SemanticMemoryState,
    SemanticMemoryTombstone,
    SemanticMemoryType,
)


class SemanticMemoryNotFound(LookupError):
    pass


class SemanticMemoryStateConflict(RuntimeError):
    pass


class SemanticMutationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    admission: MemoryAdmission
    memory: SemanticMemory


@dataclass(frozen=True)
class SemanticMemoryPage:
    items: list[SemanticMemory | SemanticMemoryTombstone]
    total: int
    limit: int
    offset: int


def normalize_content(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _content_hash(scope: MemoryScope, owner_user_id: str | None, content: str) -> str:
    source = "\x1f".join((scope.value, owner_user_id or "", content))
    return hashlib.sha256(source.encode()).hexdigest()


def _encode_vector(vector: EmbeddingVector) -> bytes:
    return array("f", vector.values).tobytes()


class SemanticMemoryService:
    def __init__(
        self,
        store: MemoryStore,
        embedding_provider: EmbeddingProvider,
        *,
        clock=None,
        id_factory=None,
    ):
        self.store = store
        self.embedding_provider = embedding_provider
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.id_factory = id_factory or (lambda: f"mem_{uuid4()}")

    @staticmethod
    def _row_to_memory(row) -> SemanticMemory:
        return SemanticMemory(
            memory_id=row["memory_id"],
            memory_type=row["memory_type"],
            scope=row["scope"],
            owner_user_id=row["owner_user_id"],
            content=row["content"],
            source=row["source"],
            state=row["state"],
            supersedes_memory_id=row["supersedes_memory_id"],
            superseded_by_memory_id=row["superseded_by_memory_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_confirmed_at=row["last_confirmed_at"],
            embedding_provider=row["embedding_provider"],
            embedding_model=row["embedding_model"],
        )

    @staticmethod
    def _row_to_tombstone(row) -> SemanticMemoryTombstone:
        return SemanticMemoryTombstone(
            memory_id=row["memory_id"],
            deleted_at=row["deleted_at"],
            deletion_trace_id=row["deletion_trace_id"],
        )

    @staticmethod
    def _mutation_from_json(payload: dict) -> SemanticMutationResult:
        return SemanticMutationResult.model_validate(payload)

    def get(self, memory_id: str) -> SemanticMemory | SemanticMemoryTombstone:
        with self.store.connect() as connection:
            row = connection.execute(
                "SELECT * FROM semantic_memories WHERE memory_id = ?", (memory_id,)
            ).fetchone()
            if row is not None:
                return self._row_to_memory(row)
            tombstone = connection.execute(
                "SELECT * FROM semantic_tombstones WHERE memory_id = ?", (memory_id,)
            ).fetchone()
        if tombstone is not None:
            return self._row_to_tombstone(tombstone)
        raise SemanticMemoryNotFound(memory_id)

    def _active_duplicate(self, connection, command: SemanticMemoryCreate):
        normalized = normalize_content(command.content)
        digest = _content_hash(command.scope, command.owner_user_id, normalized)
        return connection.execute(
            """
            SELECT * FROM semantic_memories
            WHERE state = 'ACTIVE' AND scope = ? AND owner_user_id IS ?
              AND content_hash = ?
            ORDER BY created_at, rowid
            LIMIT 1
            """,
            (command.scope.value, command.owner_user_id, digest),
        ).fetchone()

    def create(self, command: SemanticMemoryCreate) -> SemanticMutationResult:
        return self.create_idempotent(command).value

    def create_idempotent(
        self, command: SemanticMemoryCreate
    ) -> IdempotentResult:
        operation = "semantic.create"
        payload = command.model_dump(mode="json", exclude={"idempotency_key"})
        request_hash = OperationalContextService._request_hash(operation, payload)

        with self.store.connect() as connection:
            replay = OperationalContextService._replay(
                connection, command.idempotency_key, operation, request_hash
            )
            if replay is not None:
                return IdempotentResult(self._mutation_from_json(replay), True)
            duplicate = self._active_duplicate(connection, command)

        if duplicate is not None:
            now = self.clock().isoformat()
            with self.store.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                replay = OperationalContextService._replay(
                    connection, command.idempotency_key, operation, request_hash
                )
                if replay is not None:
                    return IdempotentResult(self._mutation_from_json(replay), True)
                duplicate = self._active_duplicate(connection, command)
                if duplicate is None:
                    return self.create_idempotent(command)
                connection.execute(
                    """
                    UPDATE semantic_memories
                    SET last_confirmed_at = ?, updated_at = ?
                    WHERE memory_id = ? AND state = 'ACTIVE'
                    """,
                    (now, now, duplicate["memory_id"]),
                )
                row = connection.execute(
                    "SELECT * FROM semantic_memories WHERE memory_id = ?",
                    (duplicate["memory_id"],),
                ).fetchone()
                result = SemanticMutationResult(
                    admission=MemoryAdmission.DUPLICATE,
                    memory=self._row_to_memory(row),
                )
                OperationalContextService._record_idempotency(
                    connection,
                    command.idempotency_key,
                    operation,
                    request_hash,
                    result.model_dump(mode="json"),
                    now,
                )
            return IdempotentResult(result, False)

        vector = self.embedding_provider.embed(command.content)
        now = self.clock().isoformat()
        memory_id = self.id_factory()
        normalized = normalize_content(command.content)
        digest = _content_hash(command.scope, command.owner_user_id, normalized)
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            replay = OperationalContextService._replay(
                connection, command.idempotency_key, operation, request_hash
            )
            if replay is not None:
                return IdempotentResult(self._mutation_from_json(replay), True)
            duplicate = self._active_duplicate(connection, command)
            if duplicate is not None:
                raise SemanticMemoryStateConflict("concurrent duplicate")
            connection.execute(
                """
                INSERT INTO semantic_memories (
                    memory_id, memory_type, scope, owner_user_id, content,
                    normalized_content, content_hash, source, state,
                    embedding, embedding_dimension, embedding_provider,
                    embedding_model, supersedes_memory_id,
                    superseded_by_memory_id, created_at, updated_at,
                    last_confirmed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?,
                          NULL, NULL, ?, ?, ?)
                """,
                (
                    memory_id,
                    command.memory_type.value,
                    command.scope.value,
                    command.owner_user_id,
                    command.content,
                    normalized,
                    digest,
                    command.source.value,
                    _encode_vector(vector),
                    len(vector.values),
                    vector.provider,
                    vector.model,
                    now,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM semantic_memories WHERE memory_id = ?", (memory_id,)
            ).fetchone()
            result = SemanticMutationResult(
                admission=MemoryAdmission.NEW, memory=self._row_to_memory(row)
            )
            OperationalContextService._record_idempotency(
                connection,
                command.idempotency_key,
                operation,
                request_hash,
                result.model_dump(mode="json"),
                now,
            )
        return IdempotentResult(result, False)

    def confirm(self, memory_id: str, idempotency_key: str) -> SemanticMemory:
        operation = f"semantic.confirm:{memory_id}"
        request_hash = OperationalContextService._request_hash(operation, {})
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            replay = OperationalContextService._replay(
                connection, idempotency_key, operation, request_hash
            )
            if replay is not None:
                return SemanticMemory.model_validate(replay)
            row = connection.execute(
                "SELECT * FROM semantic_memories WHERE memory_id = ?", (memory_id,)
            ).fetchone()
            if row is None:
                raise SemanticMemoryNotFound(memory_id)
            if row["state"] != SemanticMemoryState.ACTIVE.value:
                raise SemanticMemoryStateConflict(memory_id)
            now = self.clock().isoformat()
            connection.execute(
                "UPDATE semantic_memories SET last_confirmed_at = ?, updated_at = ? "
                "WHERE memory_id = ?",
                (now, now, memory_id),
            )
            row = connection.execute(
                "SELECT * FROM semantic_memories WHERE memory_id = ?", (memory_id,)
            ).fetchone()
            memory = self._row_to_memory(row)
            OperationalContextService._record_idempotency(
                connection,
                idempotency_key,
                operation,
                request_hash,
                memory.model_dump(mode="json"),
                now,
            )
        return memory

    def supersede(
        self,
        memory_id: str,
        replacement: SemanticMemoryCreate,
        *,
        idempotency_key: str,
    ) -> SemanticMutationResult:
        operation = f"semantic.supersede:{memory_id}"
        payload = replacement.model_dump(mode="json", exclude={"idempotency_key"})
        request_hash = OperationalContextService._request_hash(operation, payload)
        with self.store.connect() as connection:
            replay = OperationalContextService._replay(
                connection, idempotency_key, operation, request_hash
            )
            if replay is not None:
                return self._mutation_from_json(replay)
            row = connection.execute(
                "SELECT * FROM semantic_memories WHERE memory_id = ?", (memory_id,)
            ).fetchone()
        if row is None:
            raise SemanticMemoryNotFound(memory_id)
        previous = self._row_to_memory(row)
        if previous.state is not SemanticMemoryState.ACTIVE:
            raise SemanticMemoryStateConflict(memory_id)
        if (
            previous.scope is not replacement.scope
            or previous.owner_user_id != replacement.owner_user_id
        ):
            raise SemanticMemoryStateConflict("replacement scope or owner differs")

        vector = self.embedding_provider.embed(replacement.content)
        now = self.clock().isoformat()
        new_id = self.id_factory()
        normalized = normalize_content(replacement.content)
        digest = _content_hash(
            replacement.scope, replacement.owner_user_id, normalized
        )
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            replay = OperationalContextService._replay(
                connection, idempotency_key, operation, request_hash
            )
            if replay is not None:
                return self._mutation_from_json(replay)
            current = connection.execute(
                "SELECT state FROM semantic_memories WHERE memory_id = ?", (memory_id,)
            ).fetchone()
            if current is None:
                raise SemanticMemoryNotFound(memory_id)
            if current["state"] != SemanticMemoryState.ACTIVE.value:
                raise SemanticMemoryStateConflict(memory_id)
            connection.execute(
                """
                INSERT INTO semantic_memories (
                    memory_id, memory_type, scope, owner_user_id, content,
                    normalized_content, content_hash, source, state,
                    embedding, embedding_dimension, embedding_provider,
                    embedding_model, supersedes_memory_id,
                    superseded_by_memory_id, created_at, updated_at,
                    last_confirmed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?,
                          ?, NULL, ?, ?, ?)
                """,
                (
                    new_id,
                    replacement.memory_type.value,
                    replacement.scope.value,
                    replacement.owner_user_id,
                    replacement.content,
                    normalized,
                    digest,
                    replacement.source.value,
                    _encode_vector(vector),
                    len(vector.values),
                    vector.provider,
                    vector.model,
                    memory_id,
                    now,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                UPDATE semantic_memories
                SET state = 'SUPERSEDED', superseded_by_memory_id = ?, updated_at = ?
                WHERE memory_id = ?
                """,
                (new_id, now, memory_id),
            )
            row = connection.execute(
                "SELECT * FROM semantic_memories WHERE memory_id = ?", (new_id,)
            ).fetchone()
            result = SemanticMutationResult(
                admission=MemoryAdmission.SUPERSEDES,
                memory=self._row_to_memory(row),
            )
            OperationalContextService._record_idempotency(
                connection,
                idempotency_key,
                operation,
                request_hash,
                result.model_dump(mode="json"),
                now,
            )
        return result

    def delete(
        self, memory_id: str, *, idempotency_key: str, trace_id: str
    ) -> SemanticMemoryTombstone:
        return self.delete_idempotent(memory_id, idempotency_key, trace_id).value

    def delete_idempotent(
        self, memory_id: str, idempotency_key: str, trace_id: str
    ) -> IdempotentResult:
        operation = f"semantic.delete:{memory_id}"
        request_hash = OperationalContextService._request_hash(
            operation, {"trace_id": trace_id}
        )
        with self.store.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            replay = OperationalContextService._replay(
                connection, idempotency_key, operation, request_hash
            )
            if replay is not None:
                return IdempotentResult(
                    SemanticMemoryTombstone.model_validate(replay), True
                )
            row = connection.execute(
                "SELECT memory_id FROM semantic_memories WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
            if row is None:
                raise SemanticMemoryNotFound(memory_id)
            now = self.clock().isoformat()
            connection.execute(
                "DELETE FROM semantic_memories WHERE memory_id = ?", (memory_id,)
            )
            connection.execute(
                """
                INSERT INTO semantic_tombstones (
                    memory_id, deleted_at, deletion_trace_id
                ) VALUES (?, ?, ?)
                """,
                (memory_id, now, trace_id),
            )
            tombstone = SemanticMemoryTombstone(
                memory_id=memory_id,
                deleted_at=now,
                deletion_trace_id=trace_id,
            )
            OperationalContextService._record_idempotency(
                connection,
                idempotency_key,
                operation,
                request_hash,
                tombstone.model_dump(mode="json"),
                now,
            )
        return IdempotentResult(tombstone, False)

    def list_memories(
        self,
        *,
        scope: MemoryScope | str | None = None,
        owner_user_id: str | None = None,
        memory_type: SemanticMemoryType | str | None = None,
        state: SemanticMemoryState | str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> SemanticMemoryPage:
        state_value = SemanticMemoryState(state) if state is not None else None
        if state_value is SemanticMemoryState.DELETED:
            with self.store.connect() as connection:
                total = connection.execute(
                    "SELECT COUNT(*) FROM semantic_tombstones"
                ).fetchone()[0]
                rows = connection.execute(
                    "SELECT * FROM semantic_tombstones ORDER BY deleted_at, rowid "
                    "LIMIT ? OFFSET ?",
                    (limit, offset),
                ).fetchall()
            return SemanticMemoryPage(
                [self._row_to_tombstone(row) for row in rows], total, limit, offset
            )

        clauses: list[str] = []
        args: list[object] = []
        if scope is not None:
            clauses.append("scope = ?")
            args.append(MemoryScope(scope).value)
        if owner_user_id is not None:
            clauses.append("owner_user_id = ?")
            args.append(owner_user_id)
        if memory_type is not None:
            clauses.append("memory_type = ?")
            args.append(SemanticMemoryType(memory_type).value)
        if state_value is not None:
            clauses.append("state = ?")
            args.append(state_value.value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.store.connect() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM semantic_memories" + where, args
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT * FROM semantic_memories" + where
                + " ORDER BY created_at, rowid LIMIT ? OFFSET ?",
                [*args, limit, offset],
            ).fetchall()
        return SemanticMemoryPage(
            [self._row_to_memory(row) for row in rows], total, limit, offset
        )
