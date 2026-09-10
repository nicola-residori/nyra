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


@pytest.mark.asyncio
async def test_future_llm_plan_must_pass_router_to_skills_gate_before_capability():
    from router.llm_action_gate import LlmActionGate
    from shared.protocol.execution import ExecutionPlan
    from shared.protocol.execution_common import (
        ExecutionStatus,
        ExecutionStep,
        ExecutionTarget,
        NyraOperation,
        NyraResourceType,
        PlanOrigin,
        PlanValidationState,
    )
    from shared.protocol.capabilities import (
        ExecuteResponse,
        ResolveResponse,
        ResolveStatus,
        ResolveCandidate,
        ResolvedResource,
    )
    from skills.execution import ExecutionPlanExecutor

    calls = []

    class RouterCapability:
        async def resolve(self, reference, trusted_context, *, correlation):
            calls.append("router.capability.resolve")
            return ResolveResponse(
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
            )

        async def execute(self, request, trusted_context):
            calls.append("router.capability.execute")
            return ExecuteResponse(
                correlation=request.correlation,
                outcome=CommonOutcome.SUCCESS,
                result={"ok": True},
            )

        async def automation_create(self, request, trusted_context):
            raise AssertionError("not expected")

    class SkillsBoundary:
        def __init__(self):
            self.executor = ExecutionPlanExecutor(RouterCapability())

        async def validate_and_execute(self, plan, *, correlation, trusted_context):
            calls.append("skills.validate_materialize")
            validated = plan.model_copy(
                update={"validation_state": PlanValidationState.VALIDATED}
            )
            return await self.executor.execute(
                validated,
                correlation=correlation,
                trusted_context=trusted_context,
            )

    gate = LlmActionGate(SkillsBoundary())
    plan = ExecutionPlan(
        plan_id="llm-plan",
        origin=PlanOrigin.REASONING_LLM,
        validation_state=PlanValidationState.PROPOSED,
        steps=[
            ExecutionStep(
                step_id="one",
                operation=NyraOperation.TURN_ON,
                target=ExecutionTarget(
                    reference="kitchen light",
                    resource_type=NyraResourceType.LIGHT,
                ),
            )
        ],
    )
    request_id = new_request_id()
    corr = CapabilityCorrelation(
        request_id=request_id,
        origin_request_id=request_id,
        trace_id=new_trace_id(),
    )

    result = await gate.execute_proposal(
        plan,
        correlation=corr,
        trusted_context={"allowed_resource_ids": ["light.kitchen"]},
    )

    assert result.status is ExecutionStatus.COMPLETED
    assert calls == [
        "skills.validate_materialize",
        "router.capability.resolve",
        "router.capability.execute",
    ]


@pytest.mark.asyncio
async def test_llm_action_gate_rejects_non_llm_origin_before_skills_or_capability():
    from router.llm_action_gate import LlmActionGate
    from shared.protocol.execution import ExecutionPlan
    from shared.protocol.execution_common import PlanOrigin, PlanValidationState

    class SkillsBoundary:
        async def validate_and_execute(self, *args, **kwargs):
            raise AssertionError("must not be called")

    gate = LlmActionGate(SkillsBoundary())
    plan = ExecutionPlan(
        plan_id="skills-plan",
        origin=PlanOrigin.SKILLS,
        validation_state=PlanValidationState.VALIDATED,
        steps=[],
    )
    corr = CapabilityCorrelation(
        request_id=new_request_id(),
        trace_id=new_trace_id(),
    )

    with pytest.raises(ValueError, match="LLM-origin"):
        await gate.execute_proposal(plan, correlation=corr, trusted_context={})


def test_skills_configuration_cannot_contain_home_assistant_credentials():
    from dataclasses import fields
    from skills.config import SkillsSettings

    names = {field.name.casefold() for field in fields(SkillsSettings)}
    assert not any("home_assistant" in name for name in names)
    assert not any(name in {"ha_token", "home_assistant_token"} for name in names)


@pytest.mark.asyncio
async def test_identity_skill_runs_through_real_skills_registry_and_service():
    from shared.protocol.skills import SkillOutcome
    from skills.registry import SkillRegistry
    from skills.modules import register_builtin_skills
    from skills.service import SkillsService

    registry = SkillRegistry()
    register_builtin_skills(registry)
    service = SkillsService(registry=registry)
    request_id = new_request_id()
    corr = SkillCorrelation(
        request_id=request_id,
        origin_request_id=request_id,
        trace_id=new_trace_id(),
    )
    check = SkillCheckRequest(
        correlation=corr,
        text="who am i",
        language="en",
        context={
            "identity": {
                "user_id": "user-nicola",
                "display_name": "Nicola",
            }
        },
    )

    checked = await service.check(check)
    assert checked.outcome is SkillOutcome.HANDLED
    assert checked.match is not None
    assert checked.match.skill_name == "identity_query"

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
    assert executed.text == "You are Nicola."


@pytest.mark.asyncio
async def test_multi_step_plan_reports_partial_completion_through_real_executor():
    from shared.protocol.capabilities import (
        ExecuteResponse,
        ResolveCandidate,
        ResolveResponse,
        ResolveStatus,
        ResolvedResource,
    )
    from shared.protocol.execution import ExecutionPlan
    from shared.protocol.execution_common import (
        ExecutionStatus,
        ExecutionStep,
        ExecutionTarget,
        NyraOperation,
        NyraResourceType,
        PlanOrigin,
        PlanValidationState,
        StepStatus,
    )
    from skills.execution import ExecutionPlanExecutor

    class Capability:
        async def resolve(self, reference, trusted_context, *, correlation):
            entity = "light.kitchen" if "kitchen" in reference.reference else "light.office"
            return ResolveResponse(
                correlation=correlation,
                status=ResolveStatus.RESOLVED,
                reference=reference,
                candidates=[
                    ResolveCandidate(
                        resource=ResolvedResource(
                            resource_id=entity,
                            resource_type=NyraResourceType.LIGHT,
                            name=entity,
                        ),
                        score=1.0,
                    )
                ],
            )

        async def execute(self, request, trusted_context):
            if request.resource_id == "light.office":
                return ExecuteResponse(
                    correlation=request.correlation,
                    outcome=CommonOutcome.UNAVAILABLE,
                )
            return ExecuteResponse(
                correlation=request.correlation,
                outcome=CommonOutcome.SUCCESS,
            )

        async def automation_create(self, request, trusted_context):
            raise AssertionError("not expected")

    plan = ExecutionPlan(
        plan_id="partial",
        origin=PlanOrigin.SKILLS,
        validation_state=PlanValidationState.VALIDATED,
        steps=[
            ExecutionStep(
                step_id="kitchen",
                operation=NyraOperation.TURN_ON,
                target=ExecutionTarget(
                    reference="kitchen light",
                    resource_type=NyraResourceType.LIGHT,
                ),
            ),
            ExecutionStep(
                step_id="office",
                operation=NyraOperation.TURN_ON,
                target=ExecutionTarget(
                    reference="office light",
                    resource_type=NyraResourceType.LIGHT,
                ),
            ),
        ],
    )
    corr = CapabilityCorrelation(
        request_id=new_request_id(),
        trace_id=new_trace_id(),
    )

    result = await ExecutionPlanExecutor(Capability()).execute(
        plan,
        correlation=corr,
        trusted_context={},
    )

    assert result.status is ExecutionStatus.PARTIALLY_COMPLETED
    assert [step.status for step in result.steps] == [
        StepStatus.COMPLETED,
        StepStatus.FAILED,
    ]
