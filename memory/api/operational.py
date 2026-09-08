from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from memory.operational import IdempotencyConflict, OperationalEntryNotFound
from shared.protocol.memory import (
    MemoryScope,
    OperationalEntryCreate,
    OperationalEntryDelete,
    OperationalEntryType,
    OperationalEntryUpdate,
    OperationalResolutionRequest,
)


router = APIRouter()


def _error(status_code: int, code: str, message: str):
    return JSONResponse(
        {"error": {"code": code, "message": message}}, status_code=status_code
    )


@router.post("/v1/context/resolve")
def resolve_context(payload: OperationalResolutionRequest, request: Request):
    result = request.app.state.operational_context.resolve(payload)
    status = 409 if result.outcome.value == "AMBIGUOUS" else 200
    return JSONResponse(result.model_dump(mode="json"), status_code=status)


@router.get("/v1/operational/entries")
def list_entries(
    request: Request,
    entry_type: OperationalEntryType | None = None,
    scope: MemoryScope | None = None,
    owner_user_id: str | None = None,
    enabled: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    service = request.app.state.operational_context
    filters = {
        "entry_type": entry_type,
        "scope": scope,
        "owner_user_id": owner_user_id,
        "enabled": enabled,
    }
    items = service.list_entries(**filters, limit=limit, offset=offset)
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "total": service.count_entries(**filters),
        "limit": limit,
        "offset": offset,
    }


@router.post("/v1/operational/entries")
def create_entry(payload: OperationalEntryCreate, request: Request):
    try:
        result = request.app.state.operational_context.create_idempotent(payload)
    except IdempotencyConflict:
        return _error(409, "IDEMPOTENCY_CONFLICT", "idempotency key content differs")
    headers = {"X-Idempotent-Replay": "true"} if result.replayed else None
    return JSONResponse(
        result.value.model_dump(mode="json"),
        status_code=200 if result.replayed else 201,
        headers=headers,
    )


@router.get("/v1/operational/entries/{entry_id}")
def get_entry(entry_id: str, request: Request):
    try:
        return request.app.state.operational_context.get(entry_id)
    except OperationalEntryNotFound:
        return _error(404, "NOT_FOUND", "operational entry was not found")


@router.put("/v1/operational/entries/{entry_id}")
def update_entry(entry_id: str, payload: OperationalEntryUpdate, request: Request):
    try:
        result = request.app.state.operational_context.update_idempotent(
            entry_id, payload
        )
    except OperationalEntryNotFound:
        return _error(404, "NOT_FOUND", "operational entry was not found")
    except IdempotencyConflict:
        return _error(409, "IDEMPOTENCY_CONFLICT", "idempotency key content differs")
    headers = {"X-Idempotent-Replay": "true"} if result.replayed else None
    return JSONResponse(result.value.model_dump(mode="json"), headers=headers)


@router.delete("/v1/operational/entries/{entry_id}")
def delete_entry(entry_id: str, payload: OperationalEntryDelete, request: Request):
    try:
        result = request.app.state.operational_context.delete_idempotent(
            entry_id, payload.idempotency_key
        )
    except OperationalEntryNotFound:
        return _error(404, "NOT_FOUND", "operational entry was not found")
    except IdempotencyConflict:
        return _error(409, "IDEMPOTENCY_CONFLICT", "idempotency key content differs")
    headers = {"X-Idempotent-Replay": "true"} if result.replayed else None
    return JSONResponse(result.value, headers=headers)
