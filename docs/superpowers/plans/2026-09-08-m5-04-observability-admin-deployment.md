# M5.04 Observability, Admin, Deployment, and Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish M5 with distributed observability, Router-backed Admin diagnostics, reproducible deployment/backup/restore assets, integration regression, explicitly authorized production deployment, and authoritative documentation closure.

**Architecture:** Every Skills/capability operation emits correlated spans through the existing centralized observability model. Admin accesses Skills/jobs only through Router. Production deploys a dedicated `nyra-skills` service with persistent local state and verified rollback.

**Tech Stack:** Python 3, FastAPI, Jinja2, systemd, shell, pytest, SQLite/WAL.

**Spec:** `docs/superpowers/specs/2026-09-08-milestone-5-skills-design.md`

## Global Constraints

All constraints in the M5 master plan apply.

---

## File structure locked by this plan

Likely create:

```text
router/skills_admin.py
admin/templates/skills.html
admin/static/js/skills.js

deploy/bootstrap/skills.sh
deploy/systemd/nyra-skills.service
deploy/verify/skills.sh
deploy/backup/skills.sh
deploy/restore/skills.sh
docs/deployment/SKILLS.md

tests/admin/test_skills_pages.py
tests/router/test_skills_admin.py
tests/integration/test_m5_skills_flow.py
tests/deploy/test_skills_assets.py
```

Modify:

```text
skills/service.py
skills/jobs.py
router/app.py
router/observability/*
admin/client.py
admin/routes/pages.py
admin/templates/base.html
admin/static/css/admin.css
tests/router/*
tests/admin/*
README.md
ROADMAP.md
docs/state/CURRENT_STATE.md
docs/DEPLOYMENT.md (only if needed to link the focused Skills deployment guide)
```

Follow existing observability/deployment patterns rather than creating parallel frameworks.

### Task 15: Distributed Skills and capability observability

**Interfaces:**
Required operation names include:

```text
skills.check
skills.execute
skills.plan.validate
skills.plan.execute
skills.job.schedule
skills.job.start
skills.job.complete
skills.job.fail
skills.job.cancel
skills.job.stop
ha.resolve
ha.execute
ha.automation.create
ha.automation.update
ha.automation.delete
```

Each operation gets its own `span_id`; distributed calls share trace and parent-child correlation. Async jobs retain `origin_request_id`.

- [ ] **Step 1: Write RED**

Add tests proving:
- Skills check and execution spans differ;
- Router capability span is child-correlated to Skills-triggered operation;
- async job has null current request where appropriate and original request linkage;
- no secret HA token/raw auth header enters logs;
- local deterministic processing maps to speaker semantic stage `PROCESSING_LOCAL`;
- protected capability use maps to `USING_TOOL`.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/router tests/skills tests/integration/test_m5_skills_flow.py -k "observability or span or stage"
```

- [ ] **Step 3: Implement through existing observability abstractions**

Do not create a second logging database or Skills-specific Admin data store.

- [ ] **Step 4: GREEN + regression**

```bash
pytest -q tests/router tests/skills tests/integration/test_m5_skills_flow.py
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add skills router tests
git commit -m "feat: add skills distributed observability"
```

### Task 16: Router-backed Admin Skills and Jobs diagnostics

**Interfaces:**
- Admin -> Router only.
- No Admin direct Skills DB/API access.
- No HA credentials.
- Views show service status, registered skill metadata, jobs/status/error/correlation, and capability diagnostics sufficient for troubleshooting.
- No standalone legacy Skills UI.

- [ ] **Step 1: Write RED**

Tests must prove:
- `/skills` page exists;
- navigation includes Skills;
- Admin client calls Router endpoint;
- job list is rendered with status/timestamps/correlation;
- raw HA token is never returned/rendered;
- no direct SQLite path exists in Admin code.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/admin/test_skills_pages.py tests/router/test_skills_admin.py
```

- [ ] **Step 3: Implement Router admin facade and Admin page**

Follow M4 Memory Admin and Speaker-ID Admin patterns.

- [ ] **Step 4: GREEN + regression**

```bash
pytest -q tests/admin tests/router/test_skills_admin.py
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add router/skills_admin.py router/app.py admin tests/admin tests/router
git commit -m "feat: add skills admin diagnostics"
```

### Task 17: Deployment, systemd, backup, restore, and verification assets

**Interfaces:**
Expected service layout follows existing repository service conventions and the approved M5 design. Do not infer production IP/credentials from old chat history; deployment values must come from repo or explicit production inspection at deployment time.

Expected assets:

```text
deploy/bootstrap/skills.sh
deploy/systemd/nyra-skills.service
deploy/verify/skills.sh
deploy/backup/skills.sh
deploy/restore/skills.sh
docs/deployment/SKILLS.md
```

- [ ] **Step 1: Write declarative validation tests**

This task is primarily deployment/configuration, so do not fabricate an artificial behavior RED. Add tests/validators that prove:
- systemd unit starts the correct app;
- bootstrap installs required files/directories and is repeatable;
- data directory survives application replacement;
- backup includes persistent job DB/config needed for recovery;
- restore refuses unsafe overwrite or requires explicit target;
- verifier checks `/health`, `/ready`, service enabled/active, writable persistent store;
- scripts use `set -euo pipefail`.

- [ ] **Step 2: Run validation tests**

```bash
pytest -q tests/deploy/test_skills_assets.py
```

Expected before assets exist: failure due missing files.

- [ ] **Step 3: Implement assets**

Mirror the repository's Router/Memory/Speaker-ID deployment patterns where they exist. Service process convention must remain compatible with the project; do not introduce Docker/Kubernetes.

- [ ] **Step 4: Validate**

```bash
pytest -q tests/deploy/test_skills_assets.py
bash -n deploy/bootstrap/skills.sh
bash -n deploy/verify/skills.sh
bash -n deploy/backup/skills.sh
bash -n deploy/restore/skills.sh
git diff --check
```

- [ ] **Step 5: Commit**

```bash
git add deploy docs/deployment tests/deploy
git commit -m "feat: add skills deployment and rollback assets"
```

### Task 18: M5 integration and full regression

**Interfaces:**
One test flow must exercise the real in-process service boundaries/fakes for protected externals:

```text
request
-> trusted Router context
-> Skills check
-> optional memory gate
-> resolve target through Router capability
-> execute or clarify
-> correlated result
```

And a future LLM proposal gate test must prove:

```text
LLM proposed ExecutionPlan
-> Router
-> Skills validate/materialize
-> Router capability
```

No LLM-proposed side effect may bypass Skills.

- [ ] **Step 1: Add integration RED where missing**

Required integration cases:
- identity Skill;
- ordinary HA action;
- ambiguous target clarification;
- multi-step partial completion;
- delayed ephemeral job;
- persistent Behavior;
- explicit remember;
- explicit forget ambiguity;
- only MISS -> LLM;
- LLM-proposed action -> Skills gate -> Router capability;
- direct Skills -> HA impossible by construction/config.

- [ ] **Step 2: Run focused integration**

```bash
pytest -q tests/integration/test_m5_skills_flow.py
```

- [ ] **Step 3: Fix only real gaps with local RED/GREEN cycles**

For any failure requiring behavior change, first isolate a focused failing test, then implement minimal fix, then rerun.

- [ ] **Step 4: Full regression**

```bash
pytest -q
git diff --check
git status --short
```

Expected: full suite green, clean after commits.

- [ ] **Step 5: Request code review / self-review gate**

Use `superpowers:requesting-code-review` before merge/integration to main. Resolve review feedback with `superpowers:receiving-code-review` if needed.

Commit any test-only integration additions:

```bash
git add tests
git commit -m "test: cover M5 skills integration"
```

### Task 19: Production deployment — explicit authorization gate

**This task MUST NOT start without Nicola explicitly authorizing production changes after Task 18 is green.**

- [ ] **Step 1: Inspect actual production state**

Read current repo deployment docs and inspect the target CT/service. Do not rely on remembered IPs, paths, or legacy service contents.

Capture:
- existing `nyra-skills` legacy service if present;
- service status;
- persistent files;
- ports;
- config/environment;
- disk space;
- backup destination.

- [ ] **Step 2: Create backup and prove rollback artifact**

Run the M5 backup asset against the actual target. Record artifact path/checksum. Verify restore script can inspect/validate it without destructive restore.

- [ ] **Step 3: Present deployment/rollback commands and obtain authorization**

Even though Task 19 is already production-gated, do not execute destructive replacement until the exact commands and backup are visible.

- [ ] **Step 4: Deploy**

Deploy the versioned service and Router configuration changes using repository assets. Do not edit production code ad hoc.

- [ ] **Step 5: Physical production verification**

Verify:
- Skills `/health` and `/ready`;
- Router readiness with Skills configured;
- a harmless resolve;
- one explicitly authorized HA action;
- clarification path;
- job persistence over controlled service restart;
- disposable Nyra-managed Behavior lifecycle;
- Memory management path;
- Admin diagnostics;
- logs/correlation.

- [ ] **Step 6: Reboot/persistence verification**

Where relevant, reboot/restart service/CT and repeat health/readiness plus persistence checks.

- [ ] **Step 7: Rollback verification**

Confirm backup remains available and restore instructions match deployed paths. Do not perform destructive rollback if production is healthy; verify the path non-destructively unless a rollback is actually needed.

### Task 20: Documentation and milestone closure

**Interfaces:**
- `CURRENT_STATE.md` becomes authoritative for M5 deployed state only after production verification.
- `ROADMAP.md` and README must not contradict CURRENT_STATE.
- Design/spec remains approved historical contract.

- [ ] **Step 1: Update docs after verified production evidence**

Update:
- `docs/state/CURRENT_STATE.md`;
- `ROADMAP.md`;
- `README.md` stale milestone wording;
- deployment docs with actual verified production topology only if appropriate.

Record:
- release/commit deployed;
- service role and boundary;
- persistent data/backup location at an appropriate non-secret level;
- tests run;
- production verification;
- reboot/persistence result;
- rollback artifact/procedure;
- known limitations/deferred M6 work.

- [ ] **Step 2: Documentation validation**

```bash
git diff --check
python3 - <<'PYDOC'
from pathlib import Path

for name in (
    "docs/state/CURRENT_STATE.md",
    "ROADMAP.md",
    "README.md",
    "docs/deployment/SKILLS.md",
):
    text = Path(name).read_text(encoding="utf-8")
    for marker in ("TO" + "DO", "TB" + "D"):
        if marker in text:
            print(f"{name}: contains placeholder marker {marker}")
PYDOC
```

Inspect for stale statements manually.

- [ ] **Step 3: Final full suite**

```bash
pytest -q
git diff --check
```

- [ ] **Step 4: Commit closure**

```bash
git add docs/state/CURRENT_STATE.md ROADMAP.md README.md docs/deployment
git commit -m "docs: record M5 production deployment"
```

- [ ] **Step 5: Finish branch**

Use `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch`.

After integration to main:

```bash
git checkout main
git pull --ff-only origin main
git status --short
git rev-parse --short HEAD
git rev-parse --short origin/main
```

Expected: clean working tree and identical local/remote main.

## M5 completion statement criteria

Do not call M5 complete unless all are true:
- all TDD RED/GREEN slices are evidenced;
- full suite green;
- dedicated Skills service deployed;
- Router capability boundary proven;
- no Skills direct HA/Memory;
- only MISS fallback proven;
- LLM action gate contract proven;
- jobs restart safety proven;
- Behavior lifecycle proven;
- Memory management proven;
- Admin diagnostics available;
- backup/rollback verified;
- production/reboot checks passed;
- docs aligned;
- clean `main == origin/main`.
