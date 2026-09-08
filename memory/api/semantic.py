from __future__ import annotations

from time import monotonic

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from memory.embeddings import EmbeddingModelMismatch, EmbeddingUnavailable
from memory.observability import correlation_from_headers
from memory.operational import IdempotencyConflict
from memory.semantic import SemanticMemoryNotFound, SemanticMemoryStateConflict
from shared.protocol.memory import (
    MemoryScope,
    SemanticMemoryConfirm,
    SemanticMemoryCreate,
    SemanticMemoryDelete,
    SemanticMemoryState,
    SemanticMemorySupersede,
    SemanticMemoryType,
    SemanticSearchRequest,
)


router = APIRouter()


def _error(status: int, code: str, message: str):
    return JSONResponse(
        {"error": {"code": code, "message": message}}, status_code=status
    )


def _failure(
    request, operation, correlation, started, code, status, exc, span_id=None
):
    request.app.state.memory_observability.emit(
        f"{operation.upper()}_FAILED",
        operation.lower(),
        correlation,
        result=code,
        params={"error_code": code},
        started_at=started,
        fault=True,
        span_id=span_id,
    )
    return _error(status, code, str(exc))


@router.post("/v1/semantic/search")
def search(payload: SemanticSearchRequest, request: Request):
    correlation = correlation_from_headers(request.headers)
    started = monotonic()
    start_record = request.app.state.memory_observability.emit(
        "MEMORY_SEARCH_START", "memory_search", correlation,
        params={"scopes": [scope.value for scope in payload.scopes]},
    )
    try:
        result = request.app.state.semantic_memory.search(payload)
    except EmbeddingModelMismatch as exc:
        return _failure(
            request, "MEMORY_SEARCH", correlation, started,
            "EMBEDDING_MODEL_MISMATCH", 409, exc,
            start_record.span_id,
        )
    except (EmbeddingUnavailable, RuntimeError) as exc:
        return _failure(
            request, "MEMORY_SEARCH", correlation, started,
            "UNAVAILABLE", 503, exc,
            start_record.span_id,
        )
    request.app.state.memory_observability.emit(
        "MEMORY_SEARCH_COMPLETED",
        "memory_search",
        correlation,
        result="SUCCESS",
        params={
            "result_count": len(result.items),
            "scopes": [scope.value for scope in payload.scopes],
            "model": result.query_model,
        },
        started_at=started,
        span_id=start_record.span_id,
    )
    return result


@router.get("/v1/semantic/memories")
def list_memories(
    request: Request,
    scope: MemoryScope | None = None,
    owner_user_id: str | None = None,
    memory_type: SemanticMemoryType | None = None,
    state: SemanticMemoryState | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    page = request.app.state.semantic_memory.list_memories(
        scope=scope,
        owner_user_id=owner_user_id,
        memory_type=memory_type,
        state=state,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [item.model_dump(mode="json") for item in page.items],
        "total": page.total,
        "limit": page.limit,
        "offset": page.offset,
    }


@router.get("/v1/semantic/memories/{memory_id}")
def get_memory(memory_id: str, request: Request):
    correlation = correlation_from_headers(request.headers)
    started = monotonic()
    try:
        return request.app.state.semantic_memory.get(memory_id)
    except SemanticMemoryNotFound as exc:
        return _failure(
            request, "MEMORY_LOOKUP", correlation, started, "NOT_FOUND", 404, exc
        )


@router.post("/v1/semantic/memories")
def create_memory(payload: SemanticMemoryCreate, request: Request):
    correlation = correlation_from_headers(request.headers)
    started = monotonic()
    try:
        replay = request.app.state.semantic_memory.create_idempotent(payload)
    except IdempotencyConflict as exc:
        return _failure(
            request, "MEMORY_WRITE", correlation, started,
            "IDEMPOTENCY_CONFLICT", 409, exc,
        )
    except (EmbeddingUnavailable, RuntimeError) as exc:
        return _failure(
            request, "MEMORY_WRITE", correlation, started, "UNAVAILABLE", 503, exc
        )
    result = replay.value
    request.app.state.memory_observability.emit(
        "MEMORY_WRITE_COMPLETED",
        "memory_write",
        correlation,
        result=result.admission.value,
        params={
            "memory_id": result.memory.memory_id,
            "memory_type": result.memory.memory_type.value,
            "scope": result.memory.scope.value,
            "admission": result.admission.value,
            "model": result.memory.embedding_model,
        },
        started_at=started,
    )
    headers = {"X-Idempotent-Replay": "true"} if replay.replayed else None
    status = 201 if result.admission.value == "NEW" and not replay.replayed else 200
    return JSONResponse(
        result.model_dump(mode="json"), status_code=status, headers=headers
    )


@router.post("/v1/semantic/memories/{memory_id}/confirm")
def confirm_memory(
    memory_id: str, payload: SemanticMemoryConfirm, request: Request
):
    correlation = correlation_from_headers(request.headers)
    started = monotonic()
    try:
        memory = request.app.state.semantic_memory.confirm(
            memory_id, payload.idempotency_key
        )
    except SemanticMemoryNotFound as exc:
        return _failure(
            request, "MEMORY_WRITE", correlation, started, "NOT_FOUND", 404, exc
        )
    except SemanticMemoryStateConflict as exc:
        return _failure(
            request, "MEMORY_WRITE", correlation, started, "CONFLICT", 409, exc
        )
    request.app.state.memory_observability.emit(
        "MEMORY_WRITE_COMPLETED", "memory_confirm", correlation,
        result="CONFIRMED", params={"memory_id": memory_id}, started_at=started,
    )
    return memory


@router.post("/v1/semantic/memories/{memory_id}/supersede")
def supersede_memory(
    memory_id: str, payload: SemanticMemorySupersede, request: Request
):
    correlation = correlation_from_headers(request.headers)
    started = monotonic()
    try:
        result = request.app.state.semantic_memory.supersede(
            memory_id,
            payload.replacement,
            idempotency_key=payload.idempotency_key,
        )
    except SemanticMemoryNotFound as exc:
        return _failure(
            request, "MEMORY_WRITE", correlation, started, "NOT_FOUND", 404, exc
        )
    except (SemanticMemoryStateConflict, IdempotencyConflict) as exc:
        return _failure(
            request, "MEMORY_WRITE", correlation, started, "CONFLICT", 409, exc
        )
    except (EmbeddingUnavailable, RuntimeError) as exc:
        return _failure(
            request, "MEMORY_WRITE", correlation, started, "UNAVAILABLE", 503, exc
        )
    request.app.state.memory_observability.emit(
        "MEMORY_SUPERSEDED", "memory_supersede", correlation,
        result="SUPERSEDES",
        params={"memory_id": result.memory.memory_id, "supersedes": memory_id},
        started_at=started,
    )
    return JSONResponse(result.model_dump(mode="json"), status_code=201)


@router.delete("/v1/semantic/memories/{memory_id}")
def delete_memory(
    memory_id: str, payload: SemanticMemoryDelete, request: Request
):
    correlation = correlation_from_headers(request.headers)
    started = monotonic()
    try:
        replay = request.app.state.semantic_memory.delete_idempotent(
            memory_id, payload.idempotency_key, correlation.trace_id
        )
    except SemanticMemoryNotFound as exc:
        return _failure(
            request, "MEMORY_DELETE", correlation, started, "NOT_FOUND", 404, exc
        )
    except IdempotencyConflict as exc:
        return _failure(
            request, "MEMORY_DELETE", correlation, started,
            "IDEMPOTENCY_CONFLICT", 409, exc,
        )
    tombstone = replay.value
    request.app.state.memory_observability.emit(
        "MEMORY_DELETED", "memory_delete", correlation,
        result="DELETED", params={"memory_id": memory_id}, started_at=started,
    )
    headers = {"X-Idempotent-Replay": "true"} if replay.replayed else None
    return JSONResponse(tombstone.model_dump(mode="json"), headers=headers)
