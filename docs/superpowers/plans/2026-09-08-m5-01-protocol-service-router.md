# M5.01 Protocol, Skills Service, and Router Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the M5 shared contracts, dedicated `nyra-skills` service, deterministic registry, Router client, correct fallback semantics, and migrate the identity query out of Router-local production code.

**Architecture:** Shared protocol stays split by domain. Skills is a standalone FastAPI service with a private deterministic registry and no lateral dependencies. Router receives a typed Skills client and retains lifecycle/clarification/policy ownership.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, httpx, pytest.

**Spec:** `docs/superpowers/specs/2026-09-08-milestone-5-skills-design.md`

## Global Constraints

All constraints in `docs/superpowers/plans/2026-09-08-milestone-5-skills-implementation-plan.md` apply.

---

## File structure locked by this plan

Create:

```text
shared/protocol/skills.py
skills/__init__.py
skills/app.py
skills/config.py
skills/registry.py
skills/service.py
skills/modules/__init__.py
skills/modules/identity.py
router/skills_client.py

tests/protocol/test_skills_contract.py
tests/skills/test_app.py
tests/skills/test_registry.py
tests/skills/test_identity.py
tests/router/test_skills_client.py
tests/router/test_skills_lifecycle.py
```

Modify:

```text
shared/protocol/execution.py
shared/protocol/behavior.py
shared/protocol/capabilities.py
shared/protocol/__init__.py
router/config.py
router/app.py
router/lifecycle/service.py
router/api/health.py
tests/protocol/test_execution.py
tests/protocol/test_behavior.py
tests/protocol/test_capabilities.py
tests/router/test_request_lifecycle.py
tests/router/test_health.py
```

Remove after migration is green:

```text
router/identity_skill.py
```

### Task 1: Fill the M5 shared protocol gaps

**Interfaces:**
- Produces `SkillOutcome`, `SkillCheckRequest`, `SkillCheckResponse`, `SkillExecuteRequest`, `SkillExecuteResponse`, `SkillMatch`, `JobStatus`.
- Extends `ExecutionPlan` with `behaviors`.
- Produces typed HA automation CRUD capability request/response models.
- Must avoid an `execution.py` <-> `behavior.py` circular import.

- [ ] **Step 1: Write protocol RED tests**

Create tests proving the public schema before implementation:

```python
# tests/protocol/test_skills_contract.py
from shared.protocol.skills import (
    JobStatus,
    SkillCheckRequest,
    SkillExecuteRequest,
    SkillOutcome,
)

def test_skill_outcomes_are_contract_exact():
    assert [x.value for x in SkillOutcome] == [
        "HANDLED", "MISS", "NEEDS_CLARIFICATION", "FAILED"
    ]

def test_job_running_and_unknown_outcome_are_distinct_states():
    assert JobStatus.RUNNING.value == "RUNNING"
    assert JobStatus.UNKNOWN_OUTCOME.value == "UNKNOWN_OUTCOME"
```

Add an execution contract test:

```python
def test_execution_plan_accepts_behaviors():
    plan = ExecutionPlan(
        plan_id="pln_test",
        origin=PlanOrigin.SKILLS,
        validation_state=PlanValidationState.PROPOSED,
        steps=[],
        behaviors=[],
    )
    assert plan.behaviors == []
```

Add capability tests that import and validate typed create/read/update/delete automation models. Use stable names:

```text
AutomationCreateRequest / AutomationCreateResponse
AutomationReadRequest / AutomationReadResponse
AutomationUpdateRequest / AutomationUpdateResponse
AutomationDeleteRequest / AutomationDeleteResponse
```

- [ ] **Step 2: Run RED**

```bash
pytest -q \
  tests/protocol/test_skills_contract.py \
  tests/protocol/test_execution.py \
  tests/protocol/test_behavior.py \
  tests/protocol/test_capabilities.py
```

Expected: collection/import/schema failure because M5 models and `ExecutionPlan.behaviors` do not exist yet.

- [ ] **Step 3: Implement minimal protocol**

Create `shared/protocol/skills.py` with strict Pydantic models (`extra="forbid"`), exact Skill outcome enum, correlation, match, execute, clarification payload, and Job status.

Refactor only enough protocol primitives to represent:

```python
class ExecutionPlan(BaseModel):
    plan_id: str
    origin: PlanOrigin
    validation_state: PlanValidationState
    steps: list[ExecutionStep]
    behaviors: list[Behavior] = Field(default_factory=list)
```

If a direct import creates a cycle, extract only the smallest shared primitives to a neutral module such as `shared/protocol/execution_common.py`; do not redesign unrelated protocol.

Add automation CRUD models to `shared/protocol/capabilities.py`. Requests must use Nyra-neutral automation/Behavior data and correlation; no HA token, native service payload, or arbitrary URL field is allowed.

- [ ] **Step 4: Run GREEN**

```bash
pytest -q \
  tests/protocol/test_skills_contract.py \
  tests/protocol/test_execution.py \
  tests/protocol/test_behavior.py \
  tests/protocol/test_capabilities.py
```

Expected: PASS.

- [ ] **Step 5: Refactor and regression**

```bash
pytest -q tests/protocol tests/contracts
git diff --check
```

Inspect:

```bash
git diff -- shared/protocol tests/protocol tests/contracts
```

- [ ] **Step 6: Commit**

```bash
git add shared/protocol tests/protocol tests/contracts
git commit -m "feat: add M5 skills protocol contracts"
```

### Task 2: Create the dedicated Skills service foundation

**Interfaces:**
- Produces `skills.app.create_app()`.
- `GET /health` always proves process/HTTP liveness.
- `GET /ready` proves local registry/store/scheduler essentials only.
- No HA/Memory/LLM readiness dependency.

- [ ] **Step 1: Write RED**

```python
# tests/skills/test_app.py
from fastapi.testclient import TestClient
from skills.app import create_app

def test_health_is_live():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_ready_does_not_require_external_services():
    client = TestClient(create_app())
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
```

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/skills/test_app.py
```

Expected: import failure because `skills.app` does not exist.

- [ ] **Step 3: Implement minimal service**

Create:
- `skills/config.py`: local service settings only;
- `skills/app.py`: app factory, `/health`, `/ready`;
- `skills/service.py`: orchestration shell injected with registry/job dependencies.

Do not add Home Assistant, Memory, Speaker-ID, or LLM client settings.

- [ ] **Step 4: Run GREEN**

```bash
pytest -q tests/skills/test_app.py
```

- [ ] **Step 5: Regression and commit**

```bash
pytest -q tests/skills tests/protocol
git diff --check
git add skills tests/skills
git commit -m "feat: add skills service foundation"
```

### Task 3: Add the deterministic private Skill registry

**Interfaces:**
- `SkillDefinition(name, priority, matcher, executor)`.
- `SkillRegistry.register(definition)`.
- `SkillRegistry.check(request)`.
- Duplicate/conflicting deterministic metadata makes readiness fail.

- [ ] **Step 1: Write RED**

Tests must prove:
- deterministic priority/order;
- duplicate stable name rejected;
- ambiguous equal-priority match is an error/readiness failure rather than random dispatch;
- Router-visible result contains skill metadata but Router never chooses a module.

Example:

```python
def test_equal_priority_conflict_is_rejected():
    registry = SkillRegistry()
    registry.register(fake_skill("a", priority=100, matches=True))
    registry.register(fake_skill("b", priority=100, matches=True))
    with pytest.raises(SkillRegistryConflict):
        registry.check(request())
```

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/skills/test_registry.py
```

Expected: missing registry symbols.

- [ ] **Step 3: Implement minimal registry**

No plugin discovery, dynamic code loading, database-installed modules, or arbitrary imports in v1. Registry population is static Python wiring.

- [ ] **Step 4: GREEN + refactor**

```bash
pytest -q tests/skills/test_registry.py tests/skills/test_app.py
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add skills/registry.py skills/app.py tests/skills
git commit -m "feat: add deterministic skills registry"
```

### Task 4: Add Router -> Skills transport

**Interfaces:**
- `router.skills_client.SkillsClient`.
- Typed methods:
  - `check(request: SkillCheckRequest) -> SkillCheckResponse`
  - `execute(request: SkillExecuteRequest) -> SkillExecuteResponse`
- Router config adds Skills base URL/timeout.
- Router readiness checks Skills only when configured/enabled.

- [ ] **Step 1: Write RED**

`tests/router/test_skills_client.py` must use `httpx.MockTransport` or existing repository transport-test style and prove:
- typed path `/v1/skills/check`;
- typed path `/v1/skills/execute`;
- timeout/transport error maps to explicit service-unavailable failure, not `MISS`;
- no Home Assistant credentials are sent.

`tests/router/test_health.py` must prove configured Skills readiness participates in Router readiness.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/router/test_skills_client.py tests/router/test_health.py
```

- [ ] **Step 3: Implement minimal client/config/readiness**

Follow `router/memory_client.py` patterns rather than inventing a second HTTP abstraction.

- [ ] **Step 4: GREEN + regression**

```bash
pytest -q tests/router/test_skills_client.py tests/router/test_health.py tests/router
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add router/config.py router/skills_client.py router/api/health.py router/app.py tests/router
git commit -m "feat: connect router to skills service"
```

### Task 5: Enforce lifecycle outcome and fallback semantics

**Interfaces:**
- `MISS` is the sole automatic LLM fallback state.
- `HANDLED`, `NEEDS_CLARIFICATION`, `FAILED` terminate/continue through their own lifecycle paths.
- Transport/unavailable is never silently converted to `MISS`.

- [ ] **Step 1: Write RED**

Add focused lifecycle tests:

```python
@pytest.mark.parametrize("outcome", [
    SkillOutcome.HANDLED,
    SkillOutcome.NEEDS_CLARIFICATION,
    SkillOutcome.FAILED,
])
def test_only_miss_calls_llm(outcome):
    ...
    assert llm.calls == 0
```

And:

```python
def test_miss_calls_llm_once():
    ...
    assert llm.calls == 1
```

If the current LLM implementation is still a stub, use the lifecycle fake and assert invocation, not successful model output.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/router/test_skills_lifecycle.py tests/router/test_request_lifecycle.py
```

Expected: at least the dedicated remote Skills path or non-MISS behavior fails before wiring.

- [ ] **Step 3: Implement minimal lifecycle integration**

Replace the production `_SkillPort(IdentityQuerySkill)` path with the remote Skills client port while retaining injected fakes in tests.

Router owns pending clarification state. Do not place conversation/session state in Skills.

- [ ] **Step 4: GREEN + regression**

```bash
pytest -q tests/router/test_skills_lifecycle.py tests/router/test_request_lifecycle.py
pytest -q tests/router
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add router/app.py router/lifecycle/service.py tests/router
git commit -m "feat: enforce skills lifecycle outcomes"
```

### Task 6: Migrate identity query into `nyra-skills`

**Interfaces:**
- Private Skill module: `skills.modules.identity`.
- Preserves trusted identity semantics and localization from the existing Router-local Skill.
- Declares MemoryRequirement `NONE`.
- No semantic Memory or HA capability call.
- Does not expose technical user IDs or literal guest labels.

- [ ] **Step 1: Write RED**

Port behavior tests from the Router-local identity Skill into `tests/skills/test_identity.py`. Add an integration assertion that production Router no longer instantiates `IdentityQuerySkill`.

Test at least:
- identified trusted HA user;
- speaker-identified user;
- guest-safe response;
- request language respected;
- MemoryRequirement `NONE`.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/skills/test_identity.py tests/router/test_skills_lifecycle.py
```

Expected: identity module absent.

- [ ] **Step 3: Implement minimal module and registry wiring**

Reuse behavior, not class ownership. Move/localize the deterministic intent in Skills and register it statically.

After equivalent coverage is green, remove `router/identity_skill.py` and all production imports.

- [ ] **Step 4: GREEN + full plan regression**

```bash
pytest -q tests/skills tests/router tests/protocol tests/contracts
git diff --check
```

- [ ] **Step 5: Review deletion and commit**

```bash
git diff --stat
git diff -- router/identity_skill.py skills router tests
git add skills router tests
git commit -m "feat: move identity query into skills service"
```

## Plan 1 completion gate

Run:

```bash
pytest -q tests/protocol tests/contracts tests/skills tests/router
git diff --check
git status --short
```

Expected: all green and no uncommitted changes before Plan 2.
