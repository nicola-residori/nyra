from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import ConfigDict, Field, field_validator

from router.api.enrollments import require_auth
from router.memory_admin import enrich_memory_owners
from router.memory_client import MemoryApiError, MemoryUnavailable
from shared.protocol.memory import (
    MemoryScope,
    OperationalEntryCreate,
    OperationalEntryDelete,
    OperationalEntryType,
    OperationalEntryUpdate,
    SemanticMemoryCreate,
    SemanticMemoryConfirm,
    SemanticMemoryDelete,
    SemanticMemoryState,
    SemanticMemoryType,
    SemanticSearchRequest,
)
from shared.protocol.ids import validate_prefixed_uuid


router = APIRouter(prefix="/v1/admin/memory")


class SemanticAdminCreate(SemanticMemoryCreate):
    model_config = ConfigDict(extra="forbid")
    supersedes_memory_id: str | None = Field(default=None, min_length=1)

    @field_validator("supersedes_memory_id")
    @classmethod
    def validate_target(cls, value):
        return validate_prefixed_uuid(value, "mem") if value is not None else None


async def _call(request: Request, method: str, path: str, *, params=None, payload=None):
    require_auth(request)
    client = getattr(request.app.state, "memory_client", None)
    if client is None:
        raise HTTPException(status_code=503, detail="Memory is unavailable")
    try:
        result = await client.json(
            method, path, params=params, payload=payload
        )
    except MemoryApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from exc
    except MemoryUnavailable as exc:
        raise HTTPException(status_code=503, detail="Memory is unavailable") from exc
    return enrich_memory_owners(result, request.app.state.user_directory)


def _filters(**values):
    return {
        key: value.value if hasattr(value, "value") else value
        for key, value in values.items()
        if value is not None
    }


@router.get("/operational")
async def list_operational(
    request: Request,
    entry_type: OperationalEntryType | None = None,
    scope: MemoryScope | None = None,
    owner_user_id: str | None = None,
    enabled: bool | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await _call(
        request, "GET", "/v1/operational/entries",
        params=_filters(
            entry_type=entry_type, scope=scope, owner_user_id=owner_user_id,
            enabled=enabled, limit=limit, offset=offset,
        ),
    )


@router.post("/operational")
async def create_operational(payload: OperationalEntryCreate, request: Request):
    result = await _call(
        request, "POST", "/v1/operational/entries",
        payload=payload.model_dump(mode="json"),
    )
    return JSONResponse(result, status_code=201)


@router.get("/operational/{entry_id}")
async def get_operational(entry_id: str, request: Request):
    return await _call(request, "GET", f"/v1/operational/entries/{entry_id}")


@router.put("/operational/{entry_id}")
async def update_operational(
    entry_id: str, payload: OperationalEntryUpdate, request: Request
):
    return await _call(
        request, "PUT", f"/v1/operational/entries/{entry_id}",
        payload=payload.model_dump(mode="json"),
    )


@router.delete("/operational/{entry_id}")
async def delete_operational(
    entry_id: str, payload: OperationalEntryDelete, request: Request
):
    return await _call(
        request, "DELETE", f"/v1/operational/entries/{entry_id}",
        payload=payload.model_dump(mode="json"),
    )


@router.get("/semantic")
async def list_semantic(
    request: Request,
    scope: MemoryScope | None = None,
    owner_user_id: str | None = None,
    memory_type: SemanticMemoryType | None = None,
    state: SemanticMemoryState | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await _call(
        request, "GET", "/v1/semantic/memories",
        params=_filters(
            scope=scope, owner_user_id=owner_user_id,
            memory_type=memory_type, state=state, limit=limit, offset=offset,
        ),
    )


@router.post("/semantic")
async def create_semantic(payload: SemanticAdminCreate, request: Request):
    data = payload.model_dump(mode="json")
    target = data.pop("supersedes_memory_id", None)
    if target is None:
        result = await _call(
            request, "POST", "/v1/semantic/memories", payload=data
        )
    else:
        idempotency_key = data["idempotency_key"]
        result = await _call(
            request,
            "POST",
            f"/v1/semantic/memories/{target}/supersede",
            payload={"replacement": data, "idempotency_key": idempotency_key},
        )
    status_code = 200 if result.get("admission") == "DUPLICATE" else 201
    return JSONResponse(result, status_code=status_code)


@router.post("/semantic/search")
async def search_semantic(payload: SemanticSearchRequest, request: Request):
    return await _call(
        request, "POST", "/v1/semantic/search",
        payload=payload.model_dump(mode="json"),
    )


@router.get("/semantic/{memory_id}")
async def get_semantic(memory_id: str, request: Request):
    return await _call(request, "GET", f"/v1/semantic/memories/{memory_id}")


@router.post("/semantic/{memory_id}/confirm")
async def confirm_semantic(
    memory_id: str, payload: SemanticMemoryConfirm, request: Request
):
    return await _call(
        request, "POST", f"/v1/semantic/memories/{memory_id}/confirm",
        payload=payload.model_dump(mode="json"),
    )


@router.delete("/semantic/{memory_id}")
async def delete_semantic(
    memory_id: str, payload: SemanticMemoryDelete, request: Request
):
    return await _call(
        request, "DELETE", f"/v1/semantic/memories/{memory_id}",
        payload=payload.model_dump(mode="json"),
    )
