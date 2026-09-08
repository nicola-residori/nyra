# M5.03 Jobs, Behaviors, and Memory Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add restart-safe ephemeral Skills jobs, materialize persistent/future Behaviors as Nyra-managed Home Assistant automations, and implement explicit natural-language Memory management Skills without violating Router ownership.

**Architecture:** Skills persists only ephemeral job mechanics in its own SQLite/WAL store. Durable future/scheduled/recurring/event-driven household behavior is materialized through Router into Home Assistant. Natural-language Memory intent is recognized by Skills, but Router authorizes scope/admission and performs Memory service calls.

**Tech Stack:** Python 3, SQLite/WAL, FastAPI, Pydantic v2, pytest, Router capability APIs.

**Spec:** `docs/superpowers/specs/2026-09-08-milestone-5-skills-design.md`

## Global Constraints

All constraints in the M5 master plan apply.

---

## File structure locked by this plan

Create:

```text
skills/jobs.py
skills/job_store.py
skills/modules/delayed_action.py
skills/modules/behavior.py
skills/modules/memory_management.py
router/memory_skill_gateway.py

tests/skills/test_job_store.py
tests/skills/test_jobs.py
tests/skills/test_delayed_action.py
tests/skills/test_behavior_skill.py
tests/skills/test_memory_management.py
tests/router/test_memory_skill_gateway.py
tests/integration/test_skills_jobs.py
tests/integration/test_skills_behavior.py
tests/integration/test_skills_memory_management.py
```

Modify:

```text
skills/app.py
skills/service.py
skills/registry.py
router/ha_capability.py
router/api/capabilities.py
router/app.py
router/lifecycle/service.py
shared/protocol/capabilities.py
```

### Task 12: Persistent, restart-safe ephemeral Skill Jobs

**Interfaces:**
- `JobStore` uses SQLite WAL and a configurable local DB path.
- `JobScheduler` executes due jobs.
- States: SCHEDULED, CANCELLED, RUNNING, COMPLETED, FAILED, STOPPED, UNKNOWN_OUTCOME.
- Overdue SCHEDULED jobs run ASAP with observable delay.
- RUNNING on startup -> UNKNOWN_OUTCOME.
- Jobs preserve `origin_request_id`; delayed work may have null current `request_id`.

- [ ] **Step 1: Write storage RED**

Tests must use temporary DB and prove:
- persisted SCHEDULED survives store reopen;
- RUNNING persisted before simulated restart becomes UNKNOWN_OUTCOME on recovery;
- CANCELLED never starts;
- overdue job becomes executable immediately;
- no fabricated session/request identifiers.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/skills/test_job_store.py tests/skills/test_jobs.py
```

- [ ] **Step 3: Implement minimal store/scheduler**

Use transactions for state transitions. Store only data required to reconstruct the typed delayed action and observability correlation. No pickled Python callables.

- [ ] **Step 4: GREEN**

```bash
pytest -q tests/skills/test_job_store.py tests/skills/test_jobs.py
```

- [ ] **Step 5: Add delayed-action RED**

Prove:
- immediate first action succeeds;
- follow-up ephemeral reversal schedules a job only when semantics are truly interaction-ephemeral;
- execution later goes `Skills job -> Router capability`, never directly to HA;
- uncertain non-idempotent restart behavior is UNKNOWN_OUTCOME.

- [ ] **Step 6: Implement minimal delayed action and endpoints**

Wire:

```text
GET  /v1/jobs
GET  /v1/jobs/{job_id}
POST /v1/jobs/{job_id}/cancel
POST /v1/jobs/{job_id}/stop
```

STOP is supported only when the active effect has an explicit safe stop operation. Otherwise return typed unsupported/failed outcome; do not invent reversal.

- [ ] **Step 7: Regression and commit**

```bash
pytest -q tests/skills/test_job_store.py tests/skills/test_jobs.py tests/skills/test_delayed_action.py tests/integration/test_skills_jobs.py
git diff --check
git add skills tests/skills tests/integration
git commit -m "feat: add restart-safe skills jobs"
```

### Task 13: Materialize Behaviors through Router-owned HA automation capability

**Interfaces:**
- `ExecutionPlan.behaviors[]` and standalone Behavior use the same materialization path.
- Router capability owns HA automation CRUD.
- Nyra-created automation is tagged/identified as `managed_by=NYRA`.
- Nyra may mutate only Nyra-managed automations.
- Equivalent probable manual automation -> NEEDS_CLARIFICATION.
- ONE_SHOT success -> physical DELETE.
- ONE_SHOT failure -> KEEP with observable error.

- [ ] **Step 1: Write capability RED**

Router tests must prove typed automation create/read/update/delete behavior and reject mutation/control of manual automations.

Test the transport baseline against mocked stable HA APIs. If a required operation cannot be represented by stable HA APIs, stop this task at RED and document the exact missing capability. Only then evaluate a minimal existing HA adapter extension with Nicola; do not silently introduce one.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/router/test_ha_capability.py tests/integration/test_skills_behavior.py
```

- [ ] **Step 3: Implement minimal automation CRUD**

Internally translate platform-neutral `Behavior` to HA automation configuration. Never accept arbitrary native HA automation YAML/service payload from Skills.

Ownership metadata must be recoverable on later reads.

- [ ] **Step 4: Write Behavior Skill RED**

Scenarios:
- scheduled one-shot future action -> Behavior, not Skill Job;
- recurring action -> PERSISTENT Behavior;
- event-driven condition -> Behavior;
- simple short interaction follow-up remains a Job;
- no duration threshold is used to choose between them.

- [ ] **Step 5: Implement Skill materialization**

`skills/modules/behavior.py` constructs/validates Behavior, calls Router automation capability, and returns typed handled/clarification/failure outcomes.

- [ ] **Step 6: ONE_SHOT lifecycle RED/GREEN**

Prove success deletes the Nyra-managed automation and failure retains it with diagnosable state. Do not delete on unknown outcome.

- [ ] **Step 7: Regression and commit**

```bash
pytest -q tests/skills/test_behavior_skill.py tests/router/test_ha_capability.py tests/integration/test_skills_behavior.py
pytest -q tests/skills tests/router
git diff --check
git add skills router tests
git commit -m "feat: materialize skills behaviors in home assistant"
```

### Task 14: Natural-language Memory management Skills

**Interfaces:**
- Skills recognizes explicit remember/forget/supersede intent.
- Router decides trusted user/scope/admission and calls `nyra-memory`.
- Similarity alone never authorizes deletion/replacement.
- One unambiguous target may mutate; multiple plausible targets -> NEEDS_CLARIFICATION; none -> NOT_FOUND.
- Explicit remember is synchronous and confirmed only after storage success.

- [ ] **Step 1: Write Skills interpretation RED**

Cover:
- `"remember that my preferred temperature is 21 degrees"` -> structured remember candidate;
- `"forget my preferred temperature"` -> destructive lookup request, not immediate deletion;
- superseding explicit information -> structured supersede candidate;
- unrelated prose -> MISS.

Do not allow the Skill to choose another user's scope/identity from text.

- [ ] **Step 2: Write Router policy RED**

Use existing M4 Memory fake/client patterns to prove:
- canonical identity/scope comes from Router context;
- guest cannot claim another user's USER scope;
- one exact/unambiguous destructive candidate can proceed;
- multiple candidates => clarification;
- semantic score alone never triggers delete;
- Memory unavailable on explicit synchronous remember yields failure/unavailable, not false confirmation.

- [ ] **Step 3: Run RED**

```bash
pytest -q tests/skills/test_memory_management.py tests/router/test_memory_skill_gateway.py tests/integration/test_skills_memory_management.py
```

- [ ] **Step 4: Implement minimal Skills interpretation**

No direct Memory client in `skills/`. The output is a typed requested operation for Router.

- [ ] **Step 5: Implement Router Memory gateway**

Reuse existing `router/memory_client.py` structured APIs. Do not duplicate M4 admission or storage rules in Skills.

- [ ] **Step 6: GREEN + regression**

```bash
pytest -q tests/skills/test_memory_management.py tests/router/test_memory_skill_gateway.py tests/integration/test_skills_memory_management.py
pytest -q tests/memory tests/router tests/skills
git diff --check
```

- [ ] **Step 7: Commit**

```bash
git add skills/modules/memory_management.py router/memory_skill_gateway.py router tests
git commit -m "feat: add natural language memory management skills"
```

## Plan 3 completion gate

```bash
pytest -q tests/skills tests/router tests/memory tests/integration/test_skills_jobs.py tests/integration/test_skills_behavior.py tests/integration/test_skills_memory_management.py
git diff --check
git status --short
```
