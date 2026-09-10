import json

import httpx
import pytest

from shared.protocol.capabilities import (
    AutomationCreateResponse,
    CapabilityCorrelation,
)
from shared.protocol.common import CommonOutcome
from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCorrelation,
    SkillExecuteRequest,
    SkillOutcome,
)
from skills.modules import register_builtin_skills
from skills.modules.home_assistant import RouterHomeAssistantCapabilityClient
from skills.registry import SkillRegistry
from skills.service import SkillsService


@pytest.mark.asyncio
async def test_behavior_skill_calls_only_router_automation_capability():
    seen = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        seen.append((request.method, request.url.path, body))
        payload = body["request"]
        return httpx.Response(
            200,
            json=AutomationCreateResponse(
                correlation=CapabilityCorrelation.model_validate(
                    payload["correlation"]
                ),
                outcome=CommonOutcome.SUCCESS,
                automation_id="nyra_daily",
                behavior=payload["behavior"],
            ).model_dump(mode="json"),
        )

    capability = RouterHomeAssistantCapabilityClient(
        "http://router",
        transport=httpx.MockTransport(handler),
    )
    registry = SkillRegistry()
    register_builtin_skills(
        registry,
        home_assistant_capability=capability,
    )
    service = SkillsService(registry=registry)

    request_id = new_request_id()
    corr = SkillCorrelation(
        request_id=request_id,
        origin_request_id=request_id,
        trace_id=new_trace_id(),
    )
    check = SkillCheckRequest(
        correlation=corr,
        text="turn on the kitchen light every day at 07:30",
        language="en",
        context={"allowed_resource_ids": ["light.kitchen"]},
    )
    checked = await service.check(check)

    assert checked.outcome is SkillOutcome.HANDLED
    assert checked.match.skill_name == "behavior"

    executed = await service.execute(
        SkillExecuteRequest(
            correlation=corr,
            match=checked.match,
            text=check.text,
            language=check.language,
            context=check.context,
        )
    )

    assert executed.outcome is SkillOutcome.HANDLED
    assert seen[0][0:2] == (
        "POST",
        "/v1/capabilities/home-assistant/automations/create",
    )
    assert "home_assistant_token" not in seen[0][2]
    assert "ha_token" not in seen[0][2]


@pytest.mark.asyncio
async def test_delayed_interaction_still_selects_job_skill_not_behavior(tmp_path):
    from skills.job_store import JobStore
    from skills.jobs import JobScheduler

    class Capability:
        async def resolve(self, reference, trusted_context, *, correlation):
            raise AssertionError("check phase must not resolve")
        async def execute(self, request, trusted_context):
            raise AssertionError("check phase must not execute")
        async def automation_create(self, request, trusted_context):
            raise AssertionError("delayed interaction must not materialize behavior")

    capability = Capability()
    scheduler = JobScheduler(
        JobStore(str(tmp_path / "jobs.sqlite3")),
        capability,
    )
    registry = SkillRegistry()
    register_builtin_skills(
        registry,
        home_assistant_capability=capability,
        job_scheduler=scheduler,
    )
    service = SkillsService(registry=registry)

    request_id = new_request_id()
    corr = SkillCorrelation(
        request_id=request_id,
        origin_request_id=request_id,
        trace_id=new_trace_id(),
    )
    checked = await service.check(
        SkillCheckRequest(
            correlation=corr,
            text="turn on the kitchen light and turn it off after 2 hours",
            language="en",
            context={},
        )
    )

    assert checked.outcome is SkillOutcome.HANDLED
    assert checked.match.skill_name == "delayed_action"
