# Milestone 6 — LLM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-10-milestone-6-llm-design.md`

**Goal:** Deliver a dedicated provider-independent `nyra-llm`, Router-owned bounded reasoning/capabilities/clarification, Skills-gated side effects, diagnostics and reproducible deployment.

**Architecture:** Four ordered vertical plans: protocol/service; Router reasoning; action gate; observability/Admin/deployment. Shared contracts precede consumers. No lateral first-level calls.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, httpx, pytest, LiteLLM behind a Nyra-owned adapter.

## Global Constraints
- Work only on `m6-llm`; no `main` merge without explicit authorization.
- TDD for every functional slice: permanent RED → minimal implementation → GREEN → regressions → `git diff --check` → scope review → commit/push.
- Only `Skills CHECK -> MISS` may enter REASONING.
- Router owns trust, context, conversation, clarification, capability execution, Memory policy, max rounds and total timeout.
- `nyra-llm` owns provider/model/fallback; Router never selects them.
- Capabilities are exactly `SEARCH_MEMORY`, `READ_STATE`, `READ_ATTRIBUTE`, `DISCOVER_RESOURCES`; default max rounds = 3.
- Side effects: `REASONING_LLM` + `PROPOSED` → Router gate → Skills validation/materialization → Router capability.
- Buffered only; automatic `MEMORY_EXTRACTION` and token streaming are out of scope.
- No normal persistence of full prompt/history/Memory payload/chain-of-thought/credentials.
- No production change without explicit deployment authorization.

## Review Focus
1. Stale/cross-trace `reasoning_id` is rejected — Plan 02.
2. Unknown/side-effect capability never reaches a backend — Plan 02.
3. Valid semantic `FAILED`/low confidence never triggers fallback — Plan 01.
4. Skills execute-stage MISS/failure never reaches LLM — Plan 02.
5. Error diagnostics never leak prompt/history/Memory content — Plan 04.

## Ordered Plans
1. `2026-09-26-m6-01-protocol-llm-service.md` — contracts, `llm/`, provider abstraction/fallback, semantic/reasoning API.
2. `2026-09-26-m6-02-router-reasoning-capabilities.md` — strict MISS, client/context, bounded loop, read capabilities, clarification.
3. `2026-09-26-m6-03-action-gate.md` — Skills plan validation/materialization and Router-owned execution.
4. `2026-09-26-m6-04-observability-admin-deployment.md` — privacy-safe diagnostics, Admin, deployment/rollback and production gates.

## Closure
After all four plans: fresh full suite; `git diff --check`; branch review/push; present exact production change/backup/rollback; wait for authorization; deploy and physically verify; update CURRENT_STATE/ROADMAP/README/architecture/deployment docs from observed facts; request final merge authorization; only then merge and verify `main == origin/main`.
