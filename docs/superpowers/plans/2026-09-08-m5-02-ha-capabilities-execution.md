# M5.02 Home Assistant Capabilities and Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Router-owned Home Assistant resolution/execution capabilities, the first deterministic HA action Skill, clarification-safe target resolution, and multi-step ExecutionPlan execution.

**Architecture:** Skills sends semantic Nyra resource references to Router. Router resolves and revalidates targets, owns HA credentials, translates Nyra operations to stable HA APIs, and returns typed outcomes. Skills never sees HA tokens or sends native HA service calls.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, httpx, pytest, Home Assistant REST/WebSocket APIs where justified.

**Spec:** `docs/superpowers/specs/2026-09-08-milestone-5-skills-design.md`

## Global Constraints

All constraints in the M5 master plan apply.

---

## File structure locked by this plan

Create:

```text
router/ha_capability.py
router/api/capabilities.py
skills/modules/home_assistant.py
skills/execution.py

tests/router/test_ha_capability.py
tests/router/test_ha_capability_api.py
tests/skills/test_home_assistant_skill.py
tests/skills/test_execution.py
tests/integration/test_skills_ha_flow.py
```

Modify as needed:

```text
router/app.py
router/config.py
skills/registry.py
skills/service.py
router/lifecycle/service.py
shared/protocol/capabilities.py
tests/router/test_request_lifecycle.py
```

Home Assistant custom component remains out of scope unless a later focused RED proves stable HA APIs are insufficient.

### Task 7: Router-owned Home Assistant Resolve Capability

**Interfaces:**
- `HomeAssistantCapabilityPort.resolve(ResourceReference, trusted_context) -> ResolveResponse`.
- `HomeAssistantApiClient` owns HA base URL/token.
- Skills receives `RESOLVED`, `AMBIGUOUS`, or `NOT_FOUND`.
- `ONE` and explicit `MANY` cardinality only.

- [ ] **Step 1: Write security/ownership RED**

Tests must prove:
- Skills configuration has no HA URL/token fields.
- resolving `"kitchen light"` calls Router capability, not HA from Skills;
- policy-filtered candidates only;
- ONE: 0 -> NOT_FOUND, 1 -> RESOLVED, >1 -> AMBIGUOUS;
- resolved target remains stable for an execution attempt.

Example boundary assertion:

```python
def test_skills_has_no_home_assistant_credentials():
    fields = SkillsSettings.model_fields
    assert "home_assistant_url" not in fields
    assert "home_assistant_token" not in fields
```

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/router/test_ha_capability.py tests/router/test_ha_capability_api.py
```

- [ ] **Step 3: Implement minimal Router capability**

Use stable HA state/entity APIs through `HomeAssistantApiClient`. Keep native HA responses private to Router. Map to `ResolvedResource`.

Do not add a generic `call_service(domain, service, payload)` public capability.

- [ ] **Step 4: GREEN + regression**

```bash
pytest -q tests/router/test_ha_capability.py tests/router/test_ha_capability_api.py
pytest -q tests/router
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add router/ha_capability.py router/api/capabilities.py router/app.py router/config.py tests/router
git commit -m "feat: add router home assistant resolve capability"
```

### Task 8: Router-owned Home Assistant Execute Capability

**Interfaces:**
- `execute(ExecuteRequest, trusted_context) -> ExecuteResponse`.
- Only Nyra operations/resource types accepted.
- Router revalidates resource existence, availability, supported operation, and policy immediately before side effect.
- Uncertain non-idempotent result -> `UNKNOWN_OUTCOME`, no blind retry.

- [ ] **Step 1: Write RED**

Parameterize operation/resource mappings for at least:
- LIGHT/SWITCH TURN_ON/TURN_OFF;
- COVER OPEN/CLOSE;
- SCRIPT/SCENE TRIGGER where supported by contract.

Security tests:
- raw native HA service name cannot be supplied;
- arbitrary URL cannot be supplied;
- TOGGLE timeout is not retried;
- TURN_ON may use transport retry only if existing transport policy makes outcome safe and observable.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/router/test_ha_capability.py tests/router/test_ha_capability_api.py
```

- [ ] **Step 3: Implement minimal operation mapping**

Keep mapping internal, e.g.:

```python
_OPERATION_MAP = {
    (NyraResourceType.LIGHT, NyraOperation.TURN_ON): ("light", "turn_on"),
    ...
}
```

The native service tuple never crosses Router API.

- [ ] **Step 4: GREEN + regression**

```bash
pytest -q tests/router/test_ha_capability.py tests/router/test_ha_capability_api.py
pytest -q tests/router tests/protocol
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add router/ha_capability.py router/api/capabilities.py tests/router
git commit -m "feat: add router home assistant execute capability"
```

### Task 9: Add the first operational HA Skill

**Interfaces:**
- Deterministic command interpretation for supported actions.
- Produces semantic target + Nyra operation.
- Calls only Router capability interface.
- Initially support a deliberately narrow grammar/surface and expand only with RED tests.

- [ ] **Step 1: Write RED**

Examples must be language-aware and avoid assistant-name assumptions. Tests should cover supported English plus the repository's existing language patterns if applicable.

Example semantic tests:

```text
"turn on the kitchen light" -> LIGHT / TURN_ON / "kitchen light"
"open the bedroom blind"    -> COVER / OPEN / "bedroom blind"
```

Also prove an unrelated question returns `MISS`, not FAILED.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/skills/test_home_assistant_skill.py
```

- [ ] **Step 3: Implement minimal deterministic matcher/executor**

Do not copy legacy direct HA resolver behavior into Skills. Skills asks Router to resolve semantic references.

- [ ] **Step 4: GREEN + integration**

```bash
pytest -q tests/skills/test_home_assistant_skill.py tests/integration/test_skills_ha_flow.py
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add skills/modules/home_assistant.py skills/registry.py tests/skills tests/integration
git commit -m "feat: add deterministic home assistant skill"
```

### Task 10: Add target clarification

**Interfaces:**
- Ambiguous resolve -> `NEEDS_CLARIFICATION`.
- Router stores pending clarification context.
- Clarification turn reuses session/request and creates a new trace.
- Skills remains conversation-stateless.

- [ ] **Step 1: Write RED**

Integration scenario:

```text
User: "turn on the lamp"
Router capability: two candidates
Skills: NEEDS_CLARIFICATION with safe candidate descriptors
Router: persists pending clarification

User: "the desk one"
same session_id
same request_id
new trace_id
resolved target -> execute exactly once
```

Also test:
- no candidate -> NOT_FOUND/appropriate non-fallback handling;
- a new unrelated intent does not accidentally consume stale clarification;
- candidate technical entity IDs are not exposed as user-facing text unless existing UI contract explicitly allows diagnostics.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/router/test_skills_lifecycle.py tests/integration/test_skills_ha_flow.py
```

- [ ] **Step 3: Implement minimal clarification handoff**

Pending state remains in Router lifecycle/session storage. Skills receives only typed clarification context needed for the next check/execute.

- [ ] **Step 4: GREEN + regression**

```bash
pytest -q tests/router/test_skills_lifecycle.py tests/integration/test_skills_ha_flow.py
pytest -q tests/router tests/skills
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add router/lifecycle skills tests/router tests/integration
git commit -m "feat: add skills target clarification"
```

### Task 11: Multi-step ExecutionPlan execution

**Interfaces:**
- `skills.execution` validates and executes DAG steps through Router capability.
- Supports COMPLETED, FAILED, SKIPPED_DEPENDENCY, SKIPPED_CONDITION.
- Independent branches continue.
- Overall result may be COMPLETED or PARTIALLY_COMPLETED.
- No global rollback.

- [ ] **Step 1: Write RED**

Tests:
1. A -> B dependency success executes A then B.
2. A fails; B depending on A is SKIPPED_DEPENDENCY.
3. Independent C still executes.
4. false condition -> SKIPPED_CONDITION.
5. invalid/cyclic plan rejected before side effects.
6. no step performs direct HA call.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/skills/test_execution.py
```

- [ ] **Step 3: Implement minimal executor**

Use topological readiness from the already-validated acyclic graph. Record one result per step. Do not implement transaction rollback.

- [ ] **Step 4: GREEN + regression**

```bash
pytest -q tests/skills/test_execution.py tests/integration/test_skills_ha_flow.py
pytest -q tests/skills tests/router tests/protocol
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add skills/execution.py skills/service.py tests/skills tests/integration
git commit -m "feat: execute multi-step skills plans"
```

## Plan 2 completion gate

```bash
pytest -q tests/protocol tests/skills tests/router tests/integration/test_skills_ha_flow.py
git diff --check
git status --short
```

Do not proceed to Jobs/Behaviors until this boundary is green.
