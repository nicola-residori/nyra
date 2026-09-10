import json

import httpx
import pytest

from shared.protocol.capabilities import (
    CapabilityCorrelation,
    ExecuteResponse,
    ResolveCandidate,
    ResolveResponse,
    ResolveStatus,
    ResolvedResource,
)
from shared.protocol.common import CommonOutcome
from shared.protocol.execution_common import NyraResourceType
from shared.protocol.ids import new_request_id, new_span_id, new_trace_id
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCorrelation,
    SkillExecuteRequest,
)
from skills.modules import register_builtin_skills
from skills.modules.home_assistant import RouterHomeAssistantCapabilityClient
from skills.registry import SkillRegistry
from skills.service import SkillsService


@pytest.mark.asyncio
async def test_m5_observability_keeps_trace_and_parent_child_across_skills_capability():
    from skills.observability import SkillsObservability
    skills_records = []
    capability_calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        capability_calls.append((request.url.path, body))
        correlation = CapabilityCorrelation.model_validate(
            body.get("correlation") or body["request"]["correlation"]
        )
        assert correlation.parent_span_id is not None
        if request.url.path.endswith("/resolve"):
            reference = body["reference"]
            return httpx.Response(
                200,
                json=ResolveResponse(
                    correlation=correlation,
                    status=ResolveStatus.RESOLVED,
                    reference=reference,
                    candidates=[
                        ResolveCandidate(
                            resource=ResolvedResource(
                                resource_id="light.kitchen",
                                resource_type=NyraResourceType.LIGHT,
                                name="Kitchen Light",
                            ),
                            score=1.0,
                        )
                    ],
                ).model_dump(mode="json"),
            )
        return httpx.Response(
            200,
            json=ExecuteResponse(
                correlation=correlation,
                outcome=CommonOutcome.SUCCESS,
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
    service = SkillsService(
        registry=registry,
        observability=SkillsObservability(skills_records.append),
    )

    request_id = new_request_id()
    incoming_parent = new_span_id("ROUTER", "skills_call")
    corr = SkillCorrelation(
        request_id=request_id,
        origin_request_id=request_id,
        trace_id=new_trace_id(),
        parent_span_id=incoming_parent,
    )
    check = SkillCheckRequest(
        correlation=corr,
        text="turn on the kitchen light",
        language="en",
        context={"allowed_resource_ids": ["light.kitchen"]},
    )
    checked = await service.check(check)
    await service.execute(
        SkillExecuteRequest(
            correlation=corr,
            match=checked.match,
            text=check.text,
            language=check.language,
            context=check.context,
        )
    )

    assert [r.operation for r in skills_records] == [
        "skills.check",
        "skills.execute",
    ]
    execute_span = skills_records[-1].span_id
    assert all(
        (
            item[1].get("correlation")
            or item[1]["request"]["correlation"]
        )["parent_span_id"] == execute_span
        for item in capability_calls
    )
