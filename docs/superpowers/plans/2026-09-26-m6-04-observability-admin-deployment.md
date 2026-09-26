# M6-04 — Observability, Admin and Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-10-milestone-6-llm-design.md`

**Goal:** Add privacy-safe diagnostics/Admin and reproducible deployment/rollback, then gate production verification and milestone closure.

**Architecture:** LLM emits technical metadata only; Router correlates and exposes sanitized diagnostics to Admin. Deployment follows existing first-level service conventions. Production is a separate explicitly authorized phase.

**Tech Stack:** Existing observability/log APIs, Admin FastAPI/Jinja, systemd/bootstrap shell assets, pytest.

## Review Focus
Provider errors leak no prompt; Memory errors leak no Memory content; unknown cost is null not zero; Admin calls Router only; readiness causes no paid inference.

### Task 1: LLM technical observability
**Files:** Create `llm/observability.py`, `tests/llm/test_observability.py`; modify service/provider service and shared observability only if required.
- [ ] RED success/fallback/failure metadata and explicit absence of prompt/history/Memory/CoT.
- [ ] Implement purpose/outcome/provider/model/attempt/fallback/latency/tokens/validity/error metadata.
- [ ] GREEN all LLM tests; diff check; commit `feat: add privacy safe LLM observability`.

### Task 2: Router correlation/diagnostics API
**Files:** Modify Router observability/store as needed; create `router/api/llm_diagnostics.py`, Router tests; wire in `router/app.py`.
**Interfaces:** correlate trace/request/reasoning/attempt/capability IDs; sanitized Router-backed Admin API.
- [ ] RED correlation, nullable cost, fallback, sensitive-content exclusion on errors.
- [ ] Implement events/API.
- [ ] GREEN observability regressions; diff check; commit `feat: expose LLM diagnostics through router`.

### Task 3: Admin diagnostics
**Files:** Modify `admin/client.py`, `admin/routes/pages.py`, `admin/templates/base.html`; create `admin/templates/llm_diagnostics.html` and JS only if needed; add Admin tests using existing layout.
- [ ] RED Router-only fetch and sanitized rendering of readiness/outcome/provider/model/latency/tokens/fallback/capabilities/cost/error.
- [ ] Implement following existing Admin patterns.
- [ ] GREEN Admin regression; diff check; commit `feat: add LLM admin diagnostics`.

### Task 4: Deployment/rollback assets
**Files:** Create `deploy/systemd/nyra-llm.service`, `deploy/bootstrap/llm.sh`, `deploy/backup/llm.sh`, `deploy/restore/llm.sh`, `deploy/verify/llm.sh`, `docs/deployment/LLM.md`; deployment tests/static checks as repository convention permits.
- [ ] RED/static checks for required assets, secret-free config, backup/restore/verify.
- [ ] Implement modeled on Skills/Memory conventions; do not deploy.
- [ ] Run shell syntax/static tests; diff check; commit `ops: add nyra llm deployment assets`.

### Task 5: Branch-wide pre-production gate
- [ ] Run fresh `pytest -q`; zero failures.
- [ ] Run `git diff --check`; require clean working tree.
- [ ] Review `git diff main...m6-llm --stat` and history for M6-only scope.
- [ ] Verify no tracked provider secrets and no sensitive normal diagnostic fields.
- [ ] Push and prove HEAD == `origin/m6-llm`.
- [ ] Stop and present exact production change, backup and rollback; wait for explicit authorization.

### Task 6: Authorized production verification
- [ ] After explicit authorization, backup first and verify rollback.
- [ ] Deploy compatible LLM/Router/Skills/Admin assets.
- [ ] Verify health/readiness and restart/recovery.
- [ ] Real SEMANTIC and Skills CHECK MISS → buffered REASONING.
- [ ] Real SEARCH_MEMORY plus HA read capabilities with correlation/policy checks.
- [ ] Verify Router clarification and proposed action → Skills gate → Router capability.
- [ ] Verify forbidden capability rejection and controlled technical fallback where safe.
- [ ] Perform physical HA/speaker tests and capture evidence.

### Task 7: Documentation and final merge gate
**Files:** Update `docs/state/CURRENT_STATE.md`, `ROADMAP.md`, `README.md`, and affected architecture/deployment docs from observed facts.
- [ ] Update documentation only from verified production evidence.
- [ ] Fresh full suite + `git diff --check`.
- [ ] Commit/push docs; prove clean branch and local == remote.
- [ ] Request explicit final merge authorization.
- [ ] Only after authorization merge/push `main`; prove `main == origin/main`.
