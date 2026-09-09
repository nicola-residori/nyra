from __future__ import annotations

import httpx
import pytest

from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCorrelation,
    SkillExecuteRequest,
    SkillOutcome,
)
from skills.modules.home_assistant import (
    HomeAssistantActionSkill,
    RouterHomeAssistantCapabilityClient,
)
from skills.registry import SkillDefinition, SkillRegistry
from skills.service import SkillsService


@pytest.mark.asyncio
async def test_skills_flow_uses_router_typed_capability_only():
    calls = []

    async def router_handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.json() if False else None))

        if request.url.path.endswith("/resolve"):
            body = __import__("json").loads(request.content)
            return httpx.Response(
                200,
                json={
                    "correlation": body["correlation"],
                    "status": "RESOLVED",
                    "reference": body["reference"],
                    "candidates": [
                        {
                            "resource": {
                                "resource_id": "light.kitchen",
                                "resource_type": "LIGHT",
                                "name": "Kitchen Light",
                            },
                            "score": 1.0,
                        }
                    ],
                },
            )

        if request.url.path.endswith("/execute"):
            body = __import__("json").loads(request.content)
            return httpx.Response(
                200,
                json={
                    "correlation": body["request"]["correlation"],
                    "outcome": "SUCCESS",
                    "result": {"ok": True},
                    "error": None,
                },
            )

        return httpx.Response(404)

    capability = RouterHomeAssistantCapabilityClient(
        "http://router",
        transport=httpx.MockTransport(router_handler),
    )
    skill = HomeAssistantActionSkill(capability)
    registry = SkillRegistry()
    registry.register(
        SkillDefinition(
            name=skill.name,
            priority=skill.priority,
            matcher=skill.matches,
            executor=skill.execute,
        )
    )
    service = SkillsService(registry=registry)

    check_request = SkillCheckRequest(
        correlation=SkillCorrelation(
            request_id=new_request_id(),
            trace_id=new_trace_id(),
        ),
        text="turn on the kitchen light",
        language="en",
        context={"allowed_resource_ids": ["light.kitchen"]},
    )

    checked = await service.check(check_request)
    assert checked.outcome is SkillOutcome.HANDLED
    assert checked.match is not None

    executed = await service.execute(
        SkillExecuteRequest(
            correlation=check_request.correlation,
            match=checked.match,
            text=check_request.text,
            language=check_request.language,
            context=check_request.context,
        )
    )

    assert executed.outcome is SkillOutcome.HANDLED
    assert [path for _, path, _ in calls] == [
        "/v1/capabilities/home-assistant/resolve",
        "/v1/capabilities/home-assistant/execute",
    ]
