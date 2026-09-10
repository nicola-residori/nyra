from __future__ import annotations
from typing import Any, Protocol
from shared.protocol.capabilities import AutomationCreateRequest, CapabilityCorrelation, ExecuteRequest, ExecuteResponse, ResolveCardinality, ResolveResponse, ResolveStatus, ResourceReference
from shared.protocol.common import CommonOutcome
from shared.protocol.execution import ExecutionPlan, ExecutionResult, StepResult
from shared.protocol.execution_common import ExecutionStatus, PlanValidationState, StepStatus

class ExecutionCapability(Protocol):
    async def resolve(self, reference: ResourceReference, trusted_context: dict[str, Any], *, correlation: CapabilityCorrelation) -> ResolveResponse: ...
    async def execute(self, request: ExecuteRequest, trusted_context: dict[str, Any]) -> ExecuteResponse: ...
    async def automation_create(self, request: AutomationCreateRequest, trusted_context: dict[str, Any]): ...

class InvalidExecutionPlan(ValueError): pass

class ExecutionPlanExecutor:
    def __init__(self, capability: ExecutionCapability, *, condition_evaluator=None):
        self.capability = capability
        self.condition_evaluator = condition_evaluator or self._default_condition

    @staticmethod
    def _default_condition(expression, context):
        value = expression.strip().casefold()
        if value in {"true", "always"}: return True
        if value in {"false", "never"}: return False
        raise InvalidExecutionPlan(f"unsupported condition: {expression}")

    @staticmethod
    def validate(plan: ExecutionPlan):
        if plan.validation_state is not PlanValidationState.VALIDATED:
            raise InvalidExecutionPlan("execution plan must be VALIDATED")
        ids = [s.step_id for s in plan.steps]
        if len(ids) != len(set(ids)): raise InvalidExecutionPlan("duplicate step")
        known, graph = set(ids), {s.step_id: set(s.depends_on) for s in plan.steps}
        if any(not deps <= known or node in deps for node, deps in graph.items()):
            raise InvalidExecutionPlan("invalid dependency")
        visiting, visited = set(), set()
        def visit(node):
            if node in visiting: raise InvalidExecutionPlan("cyclic plan")
            if node in visited: return
            visiting.add(node)
            for dep in graph[node]: visit(dep)
            visiting.remove(node); visited.add(node)
        for node in graph: visit(node)

    async def execute(self, plan, *, correlation, trusted_context):
        self.validate(plan)
        by_id = {s.step_id: s for s in plan.steps}
        pending, results = set(by_id), {}
        while pending:
            ready = [s for s in plan.steps if s.step_id in pending and all(d in results for d in s.depends_on)]
            if not ready: raise InvalidExecutionPlan("plan cannot make progress")
            for step in ready:
                pending.remove(step.step_id)
                if any(results[d].status is not StepStatus.COMPLETED for d in step.depends_on):
                    results[step.step_id] = StepResult(step_id=step.step_id, status=StepStatus.SKIPPED_DEPENDENCY); continue
                condition_ok = True
                for condition in step.conditions:
                    value = self.condition_evaluator(condition, trusted_context)
                    if hasattr(value, "__await__"): value = await value
                    if not value: condition_ok = False; break
                if not condition_ok:
                    results[step.step_id] = StepResult(step_id=step.step_id, status=StepStatus.SKIPPED_CONDITION); continue
                target = step.target.resolved
                if target is None:
                    resolved = await self.capability.resolve(ResourceReference(reference=step.target.reference, resource_type=step.target.resource_type, cardinality=ResolveCardinality.ONE), trusted_context, correlation=correlation)
                    if resolved.status is not ResolveStatus.RESOLVED or len(resolved.candidates) != 1:
                        results[step.step_id] = StepResult(step_id=step.step_id, status=StepStatus.FAILED, error=f"RESOLVE_{resolved.status.value}"); continue
                    resource = resolved.candidates[0].resource
                    resource_id, resource_type = resource.resource_id, resource.resource_type
                else:
                    resource_id, resource_type = target.resource_id, target.resource_type
                response = await self.capability.execute(ExecuteRequest(correlation=correlation, operation=step.operation, resource_id=resource_id, resource_type=resource_type, parameters=step.parameters), trusted_context)
                if response.outcome is CommonOutcome.SUCCESS:
                    results[step.step_id] = StepResult(step_id=step.step_id, status=StepStatus.COMPLETED, result=response.result)
                else:
                    results[step.step_id] = StepResult(step_id=step.step_id, status=StepStatus.FAILED, error=response.error.code if response.error else response.outcome.value)
        behavior_failed = False
        for behavior in plan.behaviors:
            response = await self.capability.automation_create(
                AutomationCreateRequest(
                    correlation=correlation,
                    behavior=behavior,
                ),
                trusted_context,
            )
            if response.outcome is not CommonOutcome.SUCCESS:
                behavior_failed = True
        ordered = [results[s.step_id] for s in plan.steps]
        overall = ExecutionStatus.COMPLETED if (not behavior_failed and all(r.status is StepStatus.COMPLETED for r in ordered)) else ExecutionStatus.PARTIALLY_COMPLETED
        return ExecutionResult(plan_id=plan.plan_id, status=overall, steps=ordered)
