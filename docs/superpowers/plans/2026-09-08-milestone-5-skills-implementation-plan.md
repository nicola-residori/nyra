# Milestone 5 Skills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Nyra Milestone 5 as a dedicated deterministic `nyra-skills` service, integrated through Router-owned capabilities, with safe Home Assistant actions, clarification, ExecutionPlan/Behavior execution, ephemeral jobs, natural-language Memory management, observability, Admin diagnostics, deployment assets, and production verification.

**Architecture:** Router remains the central trust boundary and capability gateway. Skills is a first-level deterministic specialist: it never calls Home Assistant, Memory, Speaker-ID, or an LLM provider directly. Side effects flow `Skills -> Router -> protected capability`; Home Assistant credentials stay in Router. Only a Skills `MISS` may fall through to reasoning LLM.

**Tech Stack:** Python 3, FastAPI, Pydantic v2, httpx, SQLite/WAL, pytest, Home Assistant HTTP/WebSocket APIs where required, Jinja2 Admin UI, systemd.

**Spec:** `docs/superpowers/specs/2026-09-08-milestone-5-skills-design.md`

## Global Constraints

- Mandatory development loop for functional changes: RED -> GREEN -> REFACTOR.
- Write the failing test first and execute it to prove the expected failure before implementation.
- Keep every RED test permanently in the suite.
- Run focused tests after GREEN, then relevant regression tests, then `git diff --check`.
- Do not start production deployment until local implementation, full regression, deployment verification, and rollback assets are complete and Nicola explicitly authorizes production changes.
- Before any production CT/service modification, create and verify a backup/rollback path.
- `nyra-skills` must never receive Home Assistant credentials.
- `nyra-skills` must never call Home Assistant, Memory, Speaker-ID, or an LLM provider directly.
- Router owns trusted RequestContext, identity, policy, clarification state, entity resolution, and protected capabilities.
- Only `MISS` permits automatic LLM fallback. `HANDLED`, `NEEDS_CLARIFICATION`, and `FAILED` do not.
- Router knows only the `nyra-skills` service, not individual private Skill modules.
- All technical code, names, logs, docs, test data, and comments are English.
- User-facing text must respect RequestContext `language`; do not hardcode Italian.
- Never hardcode the assistant name in spoken/user-facing responses.
- No raw Home Assistant service escape hatch across the Skills boundary.
- No arbitrary duration threshold distinguishes Skill Jobs from Home Assistant Behaviors.
- A `RUNNING` persisted job found after restart becomes `UNKNOWN_OUTCOME`; never blindly re-execute it.
- Manual Home Assistant automations are readable/discoverable but not mutable, controllable, or executable by Nyra.
- Similarity alone never authorizes destructive Memory mutation.
- No standalone Skills UI; Admin remains the centralized Router-backed management surface.
- Do not modify Home Assistant custom component, ESPHome, Speaker-ID, or unrelated components unless a focused RED proves the capability cannot be delivered through stable HA APIs and the change is explicitly reviewed/authorized.

---

## Baseline and execution discipline

The approved design baseline is commit `9813537` or a descendant containing that exact design document. Before implementation:

```bash
cd ~/Develop/nyra
git fetch origin
git status --short
git branch --show-current
git rev-parse --short HEAD
git rev-parse --short origin/main
```

Expected before creating the implementation worktree: clean `main`, aligned to `origin/main`.

At execution time, use `superpowers:using-git-worktrees` to create an isolated M5 worktree and branch. Suggested branch:

```text
m5-skills
```

Do not implement M5 directly on production `main`.

## Plan set and ordering

Execute these plans strictly in order:

1. `2026-09-08-m5-01-protocol-service-router.md`
   - Tasks 1-6
   - shared protocol gaps
   - dedicated Skills service foundation
   - deterministic registry
   - Router -> Skills client
   - lifecycle/fallback semantics
   - identity Skill migration

2. `2026-09-08-m5-02-ha-capabilities-execution.md`
   - Tasks 7-11
   - Router-owned HA resolve/execute capability
   - first operational Home Assistant Skill
   - clarification
   - multi-step ExecutionPlan execution

3. `2026-09-08-m5-03-jobs-behaviors-memory.md`
   - Tasks 12-14
   - durable ephemeral Skill Jobs
   - Home Assistant Behavior materialization
   - natural-language Memory management

4. `2026-09-08-m5-04-observability-admin-deployment.md`
   - Tasks 15-20
   - distributed observability
   - Admin diagnostics
   - deployment/backup/restore
   - integration regression
   - authorized production deployment
   - documentation/closure

Each plan must finish with:
- focused test suite green;
- relevant regression suite green;
- `git diff --check` green;
- reviewed diff;
- one or more small commits whose messages are listed in that plan.

## Cross-plan interfaces

The following names are fixed across the plan set so later tasks do not invent incompatible APIs:

```text
shared.protocol.skills.SkillOutcome
shared.protocol.skills.SkillCheckRequest
shared.protocol.skills.SkillCheckResponse
shared.protocol.skills.SkillExecuteRequest
shared.protocol.skills.SkillExecuteResponse
shared.protocol.skills.SkillMatch
shared.protocol.skills.JobStatus

skills.app.create_app()
skills.registry.SkillRegistry
skills.registry.SkillDefinition
skills.service.SkillsService
skills.jobs.JobStore
skills.jobs.JobScheduler

router.skills_client.SkillsClient
router.ha_capability.HomeAssistantCapabilityPort
router.ha_capability.HomeAssistantApiClient
router.ha_capability.HomeAssistantCapabilityService
```

Router lifecycle continues to consume a Skill port with check/execute semantics; the temporary Router-local identity implementation is removed only after the dedicated Skills path has equivalent coverage.

## Required final verification

Before any production authorization request:

```bash
pytest -q
git diff --check
git status --short
```

Also execute every deployment verifier added by M5 against a local/test target. Production is a separate explicit phase and must not be implied by test success.

After authorized production deployment, verify:
- Router health/readiness;
- Skills health/readiness;
- one real harmless Home Assistant resolve;
- one explicitly authorized real operational action;
- one clarification case;
- job persistence/restart safety;
- Behavior creation/read/delete lifecycle with a disposable Nyra-managed automation;
- Admin Skills/jobs diagnostics;
- service persistence after reboot;
- backup and restore procedure is executable and documented.

Then update `docs/state/CURRENT_STATE.md`, `ROADMAP.md`, and any stale README/deployment statements, run full regression, commit/push, and require clean `main == origin/main`.
