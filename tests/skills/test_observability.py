from types import SimpleNamespace

import pytest

from shared.protocol.ids import new_request_id, new_trace_id
from shared.protocol.memory import MemoryRequirement
from shared.protocol.skills import (
    SkillCheckRequest,
    SkillCorrelation,
    SkillExecuteRequest,
    SkillMatch,
    SkillOutcome,
)


class TestSkill:
    def matches(self, request):
        return True

    def match(self, request):
        return SkillMatch(
            matched=True,
            skill_name="test_skill",
            token="test_skill",
            memory_requirement=MemoryRequirement.NONE,
        )

    def execute(self, request):
        return "ok"


class Registry:
    def __init__(self):
        self.skill = TestSkill()

    def check(self, request):
        return SimpleNamespace(skill_name="test_skill", priority=1)

    def get(self, name):
        if name != "test_skill":
            return None
        return SimpleNamespace(
            matcher=self.skill.matches,
            executor=self.skill.execute,
        )

    def is_ready(self):
        return True


def correlation():
    request_id = new_request_id()
    return SkillCorrelation(
        request_id=request_id,
        origin_request_id=request_id,
        trace_id=new_trace_id(),
    )


@pytest.mark.asyncio
async def test_skills_check_and_execute_have_distinct_correlated_spans():
    from skills.observability import SkillsObservability
    from skills.service import SkillsService

    records = []
    service = SkillsService(
        registry=Registry(),
        observability=SkillsObservability(records.append),
    )
    corr = correlation()
    checked = await service.check(
        SkillCheckRequest(
            correlation=corr,
            text="anything",
            language="en",
        )
    )
    executed = await service.execute(
        SkillExecuteRequest(
            correlation=corr,
            match=checked.match,
            text="anything",
            language="en",
        )
    )

    assert executed.outcome is SkillOutcome.HANDLED
    operations = [record.operation for record in records]
    assert operations == ["skills.check", "skills.execute"]
    assert records[0].span_id != records[1].span_id
    assert records[0].trace_id == records[1].trace_id == corr.trace_id
    assert records[1].parent_span_id == corr.parent_span_id


@pytest.mark.asyncio
async def test_execution_plan_emits_validate_and_execute_spans():
    from skills.execution import ExecutionPlanExecutor
    from skills.observability import SkillsObservability
    from shared.protocol.execution import ExecutionPlan
    from shared.protocol.execution_common import PlanOrigin, PlanValidationState

    records = []
    executor = ExecutionPlanExecutor(
        capability=SimpleNamespace(),
        observability=SkillsObservability(records.append),
    )
    plan = ExecutionPlan(
        plan_id="empty",
        origin=PlanOrigin.SKILLS,
        validation_state=PlanValidationState.VALIDATED,
        steps=[],
    )
    corr = correlation()

    result = await executor.execute(plan, correlation=corr, trusted_context={})

    assert result.status.value == "COMPLETED"
    assert [record.operation for record in records] == [
        "skills.plan.validate",
        "skills.plan.execute",
    ]
    assert records[0].span_id != records[1].span_id
