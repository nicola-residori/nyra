# M6-02 — Router Reasoning and Capabilities Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-10-milestone-6-llm-design.md`

**Goal:** Replace the Router LLM stub with a bounded policy-controlled loop entered only by Skills CHECK MISS.

**Architecture:** Router builds minimized context, calls `nyra-llm`, executes allowlisted reads, and returns capability results under one trace/reasoning operation. Router owns budgets, timeout, Memory/HA access and clarification.

**Tech Stack:** Existing Router lifecycle, httpx, Memory client, HA resolver/capability layer, pytest-asyncio.

## Review Focus
Execute-stage `llm_fallback` never invokes LLM; unknown capability never reaches backend; model cannot expand Memory scope; long history is bounded; cross-trace continuation fails.

### Task 1: Strict CHECK-only MISS
**Files:** Modify `router/lifecycle/service.py`; add regression to the existing lifecycle test module discovered locally.
- [ ] RED: CHECK=HANDLED and execute returns `llm_fallback=True`; assert LLM never called.
- [ ] Run test and observe current transitional branch fail.
- [ ] Remove execute-stage semantic fallback only.
- [ ] GREEN lifecycle regressions; diff check; commit `fix: restrict LLM fallback to skills check miss`.

### Task 2: Router LLM client/config
**Files:** Create `router/llm_client.py`, `tests/router/test_llm_client.py`; modify `router/config.py`, `router/app.py`, `.env.example`, config/readiness tests.
**Interfaces:** `LlmClient.semantic(...)`, `LlmClient.reason(...)`; LLM URL plus Router max-round/timeout config; no provider/model.
- [ ] RED typed HTTP, timeout/error mapping, config and readiness.
- [ ] Implement client/config and replace `_LlmPort` stub without recursion yet.
- [ ] GREEN focused + health/config regressions; diff check; commit `feat: connect router to nyra llm`.

### Task 3: Minimized bounded reasoning context
**Files:** Create `router/reasoning_context.py`, `tests/router/test_reasoning_context.py`; modify lifecycle.
**Interfaces:** `build_reasoning_context(...) -> ReasoningContext`.
- [ ] RED language, minimized trusted identity, relevant source/area, deterministic bounded history, exclusion of biometric/raw internals.
- [ ] Implement projection only at CHECK MISS.
- [ ] GREEN focused/lifecycle; diff check; commit `feat: build bounded LLM reasoning context`.

### Task 4: Read-only capability dispatcher
**Files:** Create `router/reasoning_capabilities.py`, `tests/router/test_reasoning_capabilities.py`; reuse/modify Memory client and existing HA resolver/capability only as needed.
**Interfaces:** `ReasoningCapabilityDispatcher.execute(...) -> CapabilityResult`; exact four-capability allowlist.
- [ ] RED each allowed capability, malformed params, unknown/side-effect rejection, guest/user Memory policy, reduced discovery and attribute minimization.
- [ ] Implement through Router-owned existing boundaries.
- [ ] GREEN focused + Memory/HA regressions; diff check; commit `feat: add read-only reasoning capabilities`.

### Task 5: Bounded reasoning orchestrator
**Files:** Create `router/reasoning.py`, `tests/router/test_reasoning_loop.py`; modify lifecycle.
**Interfaces:** `ReasoningOrchestrator.run(...) -> LifecycleDecision`; consumes LLM client/dispatcher, max rounds, total deadline.
- [ ] RED direct COMPLETED, capability rounds, recoverable capability error, 4th request → `BUDGET_EXCEEDED`, timeout, forbidden request, correlation.
- [ ] Implement max 3 rounds and monotonic total deadline.
- [ ] GREEN reasoning/lifecycle; diff check; commit `feat: orchestrate bounded LLM reasoning`.

### Task 6: Router-owned clarification
**Files:** Modify lifecycle and existing request-state models/store only as required; add `tests/router/test_llm_clarification.py`.
- [ ] RED persistence, localized question, resume, expiry→normal request, no LLM-owned session state.
- [ ] Implement minimal pending-state mapping/rebuild.
- [ ] GREEN focused + existing clarification tests; `pytest tests/router -q`.
- [ ] Diff check; commit/push `feat: support router owned LLM clarification`.
