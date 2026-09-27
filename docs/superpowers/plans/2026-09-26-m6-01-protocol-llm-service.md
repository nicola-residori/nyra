# M6-01 — Protocol and LLM Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-10-milestone-6-llm-design.md`

**Goal:** Define stable M6 wire contracts and implement provider-independent buffered inference in `nyra-llm`.

**Architecture:** Shared Pydantic models define typed requests/results. `llm/` owns prompts and provider routing through `ProviderAdapter`; `LiteLLMAdapter` is private. `reasoning_id` state is ephemeral and trace-bound.

**Tech Stack:** FastAPI, Pydantic v2, LiteLLM, pytest.

## Global Constraints
- Provider SDK/LiteLLM types never escape `llm/providers/`.
- Caller cannot choose provider/model.
- LLM never executes capabilities.
- `MEMORY_EXTRACTION` remains non-operational.

## Review Focus
Unknown enum values fail; LLM `VALIDATED` plans fail; cross-trace continuation fails; invalid structured output can technically fallback; valid reasoning `FAILED` cannot fallback.

### Task 1: Shared LLM protocol
**Files:** Create `shared/protocol/llm.py`, `tests/shared/test_llm_protocol.py`; modify protocol exports only if current convention requires.
**Interfaces:** `LlmPurpose`, `ReasoningOutcome`, `ReasoningCapability`, `ReasoningContext`, `CapabilityRequest`, `CapabilityResult`, `UsageMetadata`, `LlmRequest`, `ReasoningResult`.
- [ ] Write RED tests for 3 purposes, 4 outcomes, exact capability enum, outcome-specific payloads, and plan invariant `REASONING_LLM` + `PROPOSED`.
- [ ] Run `pytest tests/shared/test_llm_protocol.py -q`; capture intended RED.
- [ ] Implement minimal typed models.
- [ ] Run focused GREEN then `pytest tests/shared -q`.
- [ ] Run `git diff --check`; commit `feat: define M6 LLM protocol`.

### Task 2: LLM config and provider abstraction
**Files:** Create `llm/__init__.py`, `llm/config.py`, `llm/providers/{__init__,base}.py`, `tests/llm/test_config.py`, `tests/llm/test_provider_contract.py`; modify `.env.example`, `pyproject.toml`.
**Interfaces:** `LlmSettings`; `ProviderAdapter.infer(...)`; normalized provider response/errors.
- [ ] RED: primary/fallback config, required secrets/config, and absence of provider/model in Router-callable request.
- [ ] Run focused RED.
- [ ] Implement minimal settings/provider interfaces and dependency.
- [ ] GREEN `pytest tests/llm/test_config.py tests/llm/test_provider_contract.py -q`.
- [ ] Regression + diff check; commit `feat: add LLM provider abstraction`.

### Task 3: LiteLLM adapter and technical fallback
**Files:** Create `llm/providers/litellm_adapter.py`, `llm/provider_service.py`, `tests/llm/test_litellm_adapter.py`, `tests/llm/test_provider_fallback.py`.
**Interfaces:** `ProviderService.infer(...)` returns normalized result plus attempt/usage metadata.
- [ ] RED: success; timeout/5xx/eligible rate-limit/invalid structured output fallback; exhaustion; no fallback for valid `FAILED`.
- [ ] Implement minimal adapter/service.
- [ ] GREEN focused and `pytest tests/llm -q`.
- [ ] Verify LiteLLM imports isolated; diff check; commit `feat: add technical LLM provider fallback`.

### Task 4: Semantic/reasoning service and ephemeral state
**Files:** Create `llm/service.py`, `llm/reasoning_store.py`, `llm/prompts.py`, tests `test_semantic_service.py`, `test_reasoning_service.py`, `test_reasoning_store.py`.
**Interfaces:** `LlmService.semantic(...) -> SemanticResult`; `reason(...) -> ReasoningResult`; store binds `reasoning_id` to `trace_id`.
- [ ] RED: stateless SEMANTIC, language, four outcomes, create/continue ID, cross-trace rejection, terminal cleanup, no capability execution.
- [ ] Implement minimal service/store/prompts; no chain-of-thought request.
- [ ] GREEN all focused tests and `tests/llm`.
- [ ] Privacy diff review + diff check; commit `feat: implement typed LLM inference service`.

### Task 5: FastAPI, health/readiness
**Files:** Create `llm/app.py`, `tests/llm/test_api.py`, `tests/llm/test_health_ready.py`.
**Interfaces:** `POST /v1/llm/semantic`, `POST /v1/llm/reason`, `GET /health`, `GET /ready`.
- [ ] RED API tests: typed results/errors, disabled extraction, health, structural readiness without paid inference, provider/model caller override rejected.
- [ ] Implement minimal API.
- [ ] GREEN `pytest tests/llm tests/shared/test_llm_protocol.py -q`; then `pytest -q`.
- [ ] `git diff --check`, scope review; commit/push `feat: expose nyra LLM service`.
