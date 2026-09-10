import pytest

from router.app import _RemoteSkillPort
from router.lifecycle.service import ContextResult, LifecycleDecision
from shared.protocol.ids import new_request_id, new_session_id, new_trace_id
from shared.protocol.requests import (
    ExecutionType,
    NyraRequest,
    RequestInput,
    RequestStatus,
    TrustedIdentity,
)
from skills.modules import register_builtin_skills
from skills.registry import SkillRegistry
from skills.service import SkillsService


class LocalSkillsClient:
    def __init__(self, service):
        self.service = service

    async def check(self, payload):
        return await self.service.check(payload)

    async def execute(self, payload):
        return await self.service.execute(payload)


class RecordingMemoryGateway:
    def __init__(self):
        self.calls = []

    async def execute(self, *, request, context, operation, pending_state=None):
        self.calls.append(
            {
                "request": request,
                "context": context,
                "operation": operation,
                "pending_state": pending_state,
            }
        )
        return LifecycleDecision.completed("Remembered.")


@pytest.mark.asyncio
async def test_explicit_memory_intent_flows_skills_to_router_gateway_not_memory_directly():
    registry = SkillRegistry()
    register_builtin_skills(registry)
    skills = SkillsService(registry=registry)
    gateway = RecordingMemoryGateway()
    port = _RemoteSkillPort(LocalSkillsClient(skills), memory_gateway=gateway)

    request_id = new_request_id()
    request = NyraRequest(
        type=ExecutionType.HA_ASSIST,
        session_id=new_session_id(),
        request_id=request_id,
        origin_request_id=request_id,
        language="en",
        identity=TrustedIdentity(
            user_id="alice",
            provider="home_assistant",
            confidence=1.0,
        ),
        input=RequestInput(
            text="remember that my preferred temperature is 21 degrees"
        ),
    )
    context = ContextResult(
        data={
            "identity": {
                "user_id": "alice",
                "resolution_source": "TRUSTED_HA_IDENTITY",
            }
        },
        trace_id=new_trace_id(),
    )

    match = await port.check(request, context, None, None)
    assert match.matched is True
    assert match.skill_name == "memory_management"

    decision = await port.execute(match, request, context, None, None)

    assert decision.status is RequestStatus.COMPLETED
    assert decision.text == "Remembered."
    assert len(gateway.calls) == 1
    operation = gateway.calls[0]["operation"]
    assert operation["kind"] == "MEMORY_MANAGEMENT"
    assert operation["operation"] == "REMEMBER"
    assert "scope" not in operation
    assert "owner_user_id" not in operation
    assert gateway.calls[0]["context"].data["identity"]["user_id"] == "alice"


@pytest.mark.asyncio
async def test_memory_router_operation_fails_closed_when_gateway_unavailable():
    registry = SkillRegistry()
    register_builtin_skills(registry)
    skills = SkillsService(registry=registry)
    port = _RemoteSkillPort(LocalSkillsClient(skills), memory_gateway=None)

    request_id = new_request_id()
    request = NyraRequest(
        type=ExecutionType.HA_ASSIST,
        session_id=new_session_id(),
        request_id=request_id,
        origin_request_id=request_id,
        language="en",
        identity=TrustedIdentity(
            user_id="alice",
            provider="home_assistant",
            confidence=1.0,
        ),
        input=RequestInput(text="forget my preferred temperature"),
    )
    context = ContextResult(
        data={
            "identity": {
                "user_id": "alice",
                "resolution_source": "TRUSTED_HA_IDENTITY",
            }
        },
        trace_id=new_trace_id(),
    )

    match = await port.check(request, context, None, None)
    decision = await port.execute(match, request, context, None, None)

    assert decision.status is RequestStatus.FAILED
    assert decision.error["code"] == "MEMORY_UNAVAILABLE"
