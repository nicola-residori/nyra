from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from shared.protocol.capabilities import (
    AutomationCreateRequest,
    AutomationCreateResponse,
    AutomationDeleteRequest,
    AutomationDeleteResponse,
    AutomationReadRequest,
    AutomationReadResponse,
    AutomationUpdateRequest,
    AutomationUpdateResponse,
    CapabilityCorrelation,
    ResolveResponse,
    ExecuteRequest,
    ExecuteResponse,
    ResourceReference,
)


router = APIRouter(prefix="/v1/capabilities/home-assistant")


class ResolveCapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correlation: CapabilityCorrelation
    reference: ResourceReference
    trusted_context: dict[str, Any] = Field(default_factory=dict)


@router.post("/resolve", response_model=ResolveResponse)
async def resolve_home_assistant_resource(
    payload: ResolveCapabilityRequest,
    request: Request,
) -> ResolveResponse:
    return await request.app.state.ha_capability.resolve(
        payload.reference,
        payload.trusted_context,
        correlation=payload.correlation,
    )


class ExecuteCapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: ExecuteRequest
    trusted_context: dict[str, Any] = Field(default_factory=dict)


@router.post("/execute", response_model=ExecuteResponse)
async def execute_home_assistant_operation(payload: ExecuteCapabilityRequest, request: Request) -> ExecuteResponse:
    return await request.app.state.ha_capability.execute(payload.request, payload.trusted_context)

class AutomationCreateCapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: AutomationCreateRequest
    trusted_context: dict[str, Any] = Field(default_factory=dict)

class AutomationReadCapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: AutomationReadRequest
    trusted_context: dict[str, Any] = Field(default_factory=dict)

class AutomationUpdateCapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: AutomationUpdateRequest
    trusted_context: dict[str, Any] = Field(default_factory=dict)

class AutomationDeleteCapabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request: AutomationDeleteRequest
    trusted_context: dict[str, Any] = Field(default_factory=dict)

@router.post("/automations/create", response_model=AutomationCreateResponse)
async def create_home_assistant_automation(payload: AutomationCreateCapabilityRequest, request: Request) -> AutomationCreateResponse:
    return await request.app.state.ha_capability.create_automation(payload.request, payload.trusted_context)

@router.post("/automations/read", response_model=AutomationReadResponse)
async def read_home_assistant_automation(payload: AutomationReadCapabilityRequest, request: Request) -> AutomationReadResponse:
    return await request.app.state.ha_capability.read_automation(payload.request, payload.trusted_context)

@router.post("/automations/update", response_model=AutomationUpdateResponse)
async def update_home_assistant_automation(payload: AutomationUpdateCapabilityRequest, request: Request) -> AutomationUpdateResponse:
    return await request.app.state.ha_capability.update_automation(payload.request, payload.trusted_context)

@router.post("/automations/delete", response_model=AutomationDeleteResponse)
async def delete_home_assistant_automation(payload: AutomationDeleteCapabilityRequest, request: Request) -> AutomationDeleteResponse:
    return await request.app.state.ha_capability.delete_automation(payload.request, payload.trusted_context)
