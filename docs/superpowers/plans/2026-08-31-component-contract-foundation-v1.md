# Component Contract Foundation v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish the shared Component Contract v1 protocol and make `nyra-router` consume it without migrating any specialist alpha component.

**Architecture:** Add focused Pydantic models under `shared/protocol` for correlation, common outcomes/errors, service status, trusted request context, semantic structures, execution structures, behaviors, and capability primitives. Refactor Router boundaries to depend on these shared contracts while preserving the already-working Request Lifecycle behavior, central observability, and Admin integration. This plan creates the stable foundation that later Memory, Skills, LLM, Speaker-ID, Capability Gateway, and Admin-specific plans will implement against.

**Tech Stack:** Python 3.11+ runtime compatibility, FastAPI, Pydantic v2, pytest, pytest-asyncio, SQLite/WAL for current Router state/observability, existing `shared.logging` package.

**Spec:** `docs/superpowers/specs/2026-08-31-component-contract-v1-design.md`

## Global Constraints

- Common functional APIs use `/v1/...`.
- Service-to-service authentication is intentionally not implemented in v1.
- v1 assumes a trusted private network; do not add tokens, Authorization headers, or placeholder auth abstractions.
- Router is the authoritative owner of trusted RequestContext.
- No `UniversalNyraRequest` or universal response envelope.
- Every technical operation creates its own `span_id` with format `CT#operation#<8 uppercase alphanumeric>`.
- Logs from one operation share that operation's span; distributed operations share `trace_id` and use `parent_span_id`.
- `session_id = ses_<UUIDv4>`, `request_id = req_<UUIDv4>`, `trace_id = trc_<UUIDv4>`.
- Clarification keeps session/request and creates a new trace.
- New intent keeps the session and creates a new request/trace.
- `request_id` and `origin_request_id` are optional on internal correlation; `trace_id` is required for distributed technical work.
- `session_id` is not required on every downstream component call; Router/observability reconstructs session correlation centrally.
- Functional outcomes belong in typed response bodies; HTTP 4xx/5xx remains for protocol/validation/routing/unhandled server failures.
- `/health` means HTTP/process alive; `/ready` means the service can perform essential work.
- No hardcoded deployment IPs, HA URLs, service credentials, speaker names, or entity IDs.
- Configuration precedence remains `ENV -> config.yaml -> defaults`.
- Router stays lightweight and asynchronous; no embedded AI model or embeddings.
- Existing Router Request Lifecycle behavior must remain green throughout this plan.
- Existing logging redaction for `authorization`, `token`, `api_key`, `password`, `secret`, and `cookie` must remain effective.
- Default historical retention remains 30 days and is not changed by this plan.
- Repository/code/comments/docs/config/API names/log events/commit messages are English.
- This plan does not delete or recreate any existing CT.

---

## File Structure

This plan intentionally creates small protocol modules rather than one large models file.

```text
shared/
└── protocol/
    ├── __init__.py
    ├── ids.py             # ID generation/validation and CorrelationContext
    ├── common.py          # CommonOutcome and ErrorDetail
    ├── service.py         # health/readiness response contracts
    ├── context.py         # RequestContext and identity/context primitives
    ├── semantic.py        # SemanticResult and semantic-domain primitives
    ├── execution.py       # ExecutionPlan, target resolution, step/result models
    ├── behavior.py        # platform-neutral Behavior models
    └── capabilities.py    # capability correlation and typed HA primitives

router/
├── app.py                 # wire shared health/readiness and v1 routes
├── models.py              # keep Router-specific ingress/response models only
├── request_lifecycle.py   # create/consume shared correlation and RequestContext
└── observability.py       # enrich distributed logs using request/session mapping

tests/
├── protocol/
│   ├── test_ids.py
│   ├── test_common.py
│   ├── test_service.py
│   ├── test_context.py
│   ├── test_semantic.py
│   ├── test_execution.py
│   ├── test_behavior.py
│   └── test_capabilities.py
└── router/
    ├── test_request_lifecycle.py
    ├── test_health_ready.py
    └── test_observability_correlation.py
```

If an existing Router module already has one of the responsibilities above under a different exact filename, keep its existing filename and move only the model ownership described here. Do not create duplicate parallel implementations.

---

### Task 1: Add Common ID and Correlation Contracts

**Files:**
- Create: `shared/protocol/__init__.py`
- Create: `shared/protocol/ids.py`
- Create: `tests/protocol/test_ids.py`
- Modify: `pyproject.toml` only if `shared.protocol` is not already discovered by current setuptools configuration.

**Interfaces:**
- Produces:
  - `new_session_id() -> str`
  - `new_request_id() -> str`
  - `new_trace_id() -> str`
  - `new_span_id(component: str, operation: str) -> str`
  - `CorrelationContext(BaseModel)` with `request_id: str | None`, `origin_request_id: str | None`, `trace_id: str`, `parent_span_id: str | None`
- Consumed later by Router lifecycle, observability, capability models, and specialist services.

- [ ] **Step 1: Write failing tests for canonical IDs**

Create `tests/protocol/test_ids.py` with tests equivalent to:

```python
import re

from shared.protocol.ids import (
    CorrelationContext,
    new_request_id,
    new_session_id,
    new_span_id,
    new_trace_id,
)

UUID_ID = re.compile(
    r"^(ses|req|trc)_[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)

def test_uuid_ids_use_canonical_prefix_and_uuid4():
    assert UUID_ID.match(new_session_id())
    assert UUID_ID.match(new_request_id())
    assert UUID_ID.match(new_trace_id())

def test_span_id_uses_component_operation_and_eight_uppercase_chars():
    span_id = new_span_id("ROUTER", "request_lifecycle")
    assert re.fullmatch(r"ROUTER#request_lifecycle#[A-Z0-9]{8}", span_id)

def test_correlation_accepts_interactive_delayed_and_system_work():
    trace = new_trace_id()

    interactive = CorrelationContext(
        request_id=new_request_id(),
        trace_id=trace,
    )
    assert interactive.origin_request_id is None

    delayed = CorrelationContext(
        origin_request_id=new_request_id(),
        trace_id=trace,
    )
    assert delayed.request_id is None

    system = CorrelationContext(trace_id=trace)
    assert system.request_id is None
    assert system.origin_request_id is None
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```bash
pytest tests/protocol/test_ids.py -q
```

Expected: import/module errors because `shared.protocol.ids` does not exist yet.

- [ ] **Step 3: Implement the minimal canonical ID API**

Create `shared/protocol/ids.py` with:
- UUIDv4-based prefixed ID generators;
- span suffix using `secrets.choice(string.ascii_uppercase + string.digits)`;
- Pydantic validation that rejects malformed `trace_id`, malformed optional request/origin IDs, and malformed `parent_span_id` when supplied.

Do not add `session_id` to `CorrelationContext`.

- [ ] **Step 4: Re-export the public protocol symbols**

Create `shared/protocol/__init__.py` and re-export only stable public types/functions introduced by completed tasks. Avoid wildcard exports.

- [ ] **Step 5: Run focused and existing lifecycle tests**

Run:

```bash
pytest tests/protocol/test_ids.py tests/router/test_request_lifecycle.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shared/protocol tests/protocol/test_ids.py pyproject.toml
git commit -m "feat: add shared correlation contracts"
```

---

### Task 2: Add Common Outcomes, Error, Health, and Readiness Contracts

**Files:**
- Create: `shared/protocol/common.py`
- Create: `shared/protocol/service.py`
- Create: `tests/protocol/test_common.py`
- Create: `tests/protocol/test_service.py`
- Modify: `router/app.py`
- Create: `tests/router/test_health_ready.py`

**Interfaces:**
- Consumes: `shared.protocol.ids` only for package exports.
- Produces:
  - `CommonOutcome(str, Enum)`
  - `ErrorDetail(BaseModel)`
  - `ServiceState(str, Enum)`
  - `ServiceStatusResponse(BaseModel)`
  - Router `GET /health`
  - Router `GET /ready`

- [ ] **Step 1: Write failing protocol tests**

Add tests asserting exact common outcome values:

```python
from shared.protocol.common import CommonOutcome, ErrorDetail

def test_common_outcomes_are_stable_machine_values():
    assert [item.value for item in CommonOutcome] == [
        "SUCCESS",
        "DENIED",
        "NOT_FOUND",
        "AMBIGUOUS",
        "UNAVAILABLE",
        "FAILED",
        "UNSUPPORTED",
        "UNKNOWN_OUTCOME",
    ]

def test_error_detail_has_stable_code_and_optional_diagnostics():
    error = ErrorDetail(code="RESOURCE_NOT_FOUND")
    assert error.message is None
    assert error.details is None
```

Add service-model tests verifying:
- `health`/`ready` state values are explicit strings;
- `service` and `version` are mandatory;
- a not-ready response can carry a stable `reason`;
- no authentication fields exist.

- [ ] **Step 2: Run protocol tests and confirm RED**

```bash
pytest tests/protocol/test_common.py tests/protocol/test_service.py -q
```

Expected: FAIL because models do not exist.

- [ ] **Step 3: Implement common and service models**

In `shared/protocol/common.py`, define exactly the common outcomes from the spec and `ErrorDetail`.

In `shared/protocol/service.py`, define:
- `ServiceState`: `HEALTHY`, `READY`, `NOT_READY`;
- `ServiceStatusResponse` fields: `status`, `service`, `version`, optional `reason`.

Do not add generic `data`, `payload`, `result`, or authentication fields.

- [ ] **Step 4: Write Router endpoint tests before wiring them**

Create `tests/router/test_health_ready.py` using FastAPI `TestClient` against the existing Router app. Assert:

```python
def test_health_is_process_liveness(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "HEALTHY"

def test_ready_reports_router_ready(client):
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "READY"
    assert body["service"] == "nyra-router"
```

Use the existing Router test fixture if one exists; otherwise create only a local fixture in this test file.

- [ ] **Step 5: Run Router endpoint tests and confirm RED if current shape differs**

```bash
pytest tests/router/test_health_ready.py -q
```

Expected: FAIL if current Router endpoints use legacy response shapes or are absent.

- [ ] **Step 6: Wire `router/app.py` to shared response contracts**

Modify existing health/readiness routes rather than creating duplicate endpoints.

Router readiness in this foundation plan means:
- Router storage initialized;
- request lifecycle service initialized;
- observability store initialized.

Do not make readiness depend on not-yet-migrated Skills, Memory, LLM, Speaker-ID, or Home Assistant.

- [ ] **Step 7: Run tests**

```bash
pytest tests/protocol/test_common.py tests/protocol/test_service.py \
       tests/router/test_health_ready.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add shared/protocol/common.py shared/protocol/service.py \
        tests/protocol/test_common.py tests/protocol/test_service.py \
        router/app.py tests/router/test_health_ready.py shared/protocol/__init__.py
git commit -m "feat: standardize service status contracts"
```

---

### Task 3: Add Trusted RequestContext Contracts and Adapt Router Lifecycle

**Files:**
- Create: `shared/protocol/context.py`
- Create: `tests/protocol/test_context.py`
- Modify: `router/models.py`
- Modify: `router/request_lifecycle.py`
- Modify: `tests/router/test_request_lifecycle.py`

**Interfaces:**
- Consumes:
  - `new_trace_id()`
  - canonical session/request IDs already supplied by ingress;
  - existing Router lifecycle persistence.
- Produces:
  - `IdentityResolutionSource`
  - `ResolvedIdentity`
  - `RequestType`
  - `RequestContext`
  - `TemporalContext`
  - typed placeholders `OperationalContext` and `PolicyContext` that carry structured dictionaries without pretending to define Memory/Policy internals yet.

- [ ] **Step 1: Write failing RequestContext tests**

Tests must cover:
- `ha_assist`, `ha_speaker`, `job`, and `nyra_ui` request types;
- identity source values including trusted HA identity, speaker identification, session continuity, and guest fallback;
- `RequestContext` requiring session/request/trace for interactive requests;
- job context allowing no session/request;
- `source` and `area` never being identity fields.

Example core assertion:

```python
def test_source_and_identity_are_independent():
    context = RequestContext(
        session_id=new_session_id(),
        request_id=new_request_id(),
        trace_id=new_trace_id(),
        type=RequestType.HA_SPEAKER,
        language="it",
        source="nyra-soggiorno",
        area="living_room",
        identity=ResolvedIdentity(
            user_id="user-123",
            resolution_source=IdentityResolutionSource.SPEAKER_IDENTIFICATION,
        ),
    )
    assert context.source == "nyra-soggiorno"
    assert context.identity.user_id == "user-123"
```

- [ ] **Step 2: Run context tests and confirm RED**

```bash
pytest tests/protocol/test_context.py -q
```

Expected: FAIL because models do not exist.

- [ ] **Step 3: Implement `shared/protocol/context.py`**

Keep the models explicit and small.

Do not add downstream component-specific data to `RequestContext`.

Represent operational/policy context as typed wrapper models with stable top-level fields and a `values: dict[str, Any]` payload only where the foundation genuinely has not yet specified internal schemas. Do not create a universal request envelope.

- [ ] **Step 4: Write/adjust lifecycle tests to assert shared context ownership**

Add assertions to `tests/router/test_request_lifecycle.py` showing:
- ingress IDs are preserved;
- Router creates a new trace;
- clarification preserves session/request and changes trace;
- new intent gets a new request/trace;
- trusted `ha_assist` identity is kept separate from physical `source`;
- jobs do not fabricate session/request IDs.

- [ ] **Step 5: Run lifecycle tests and confirm the new assertions fail before refactor**

```bash
pytest tests/router/test_request_lifecycle.py tests/protocol/test_context.py -q
```

Expected: at least the new shared-context assertions fail.

- [ ] **Step 6: Refactor Router-specific models**

In `router/models.py`:
- keep HTTP ingress/response contracts and Router-only lifecycle types;
- import shared context/correlation types instead of redefining equivalent concepts;
- remove only duplicated models proven redundant by tests;
- preserve existing wire compatibility of `/v1/requests`.

In `router/request_lifecycle.py`:
- construct authoritative `RequestContext`;
- do not trust caller-supplied identity/policy fields outside the existing trusted ingress contract;
- preserve existing lifecycle persistence and event publication.

- [ ] **Step 7: Run lifecycle and protocol tests**

```bash
pytest tests/protocol/test_context.py tests/router/test_request_lifecycle.py \
       tests/router/test_event_broker.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add shared/protocol/context.py shared/protocol/__init__.py \
        tests/protocol/test_context.py router/models.py \
        router/request_lifecycle.py tests/router/test_request_lifecycle.py
git commit -m "refactor: centralize trusted request context"
```

---

### Task 4: Add SemanticResult Contracts

**Files:**
- Create: `shared/protocol/semantic.py`
- Create: `tests/protocol/test_semantic.py`
- Modify: `shared/protocol/__init__.py`

**Interfaces:**
- Produces:
  - `SemanticConfidence`
  - `SemanticTarget`
  - `SemanticParameter`
  - `SemanticAction`
  - `SemanticTemporal`
  - `SemanticTrigger`
  - `SemanticCondition`
  - `SemanticResult`
- Consumed later by Skills and LLM plans.

- [ ] **Step 1: Write failing schema tests**

Tests must prove:
- targets contain human references, not HA IDs;
- parameters remain generic name/value/unit/expression;
- confidence is diagnostic only;
- semantic structures cannot contain execution authorization or raw HA service payload fields.

Example:

```python
def test_semantic_target_is_reference_not_resolved_resource():
    target = SemanticTarget(reference="lampada dello studio", kind="LIGHT")
    dumped = target.model_dump()
    assert dumped["reference"] == "lampada dello studio"
    assert "resource_id" not in dumped
    assert "entity_id" not in dumped
```

Also test actions, temporal expression, triggers, conditions, and `AFTER_PREVIOUS` relation representation.

- [ ] **Step 2: Run and confirm RED**

```bash
pytest tests/protocol/test_semantic.py -q
```

- [ ] **Step 3: Implement semantic models**

Use Pydantic models with explicit optional fields matching the approved design.

Do not:
- resolve targets;
- include HA entity IDs;
- include authorization;
- include executable native service data;
- embed an ExecutionPlan.

- [ ] **Step 4: Run tests**

```bash
pytest tests/protocol/test_semantic.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/protocol/semantic.py shared/protocol/__init__.py \
        tests/protocol/test_semantic.py
git commit -m "feat: add semantic result contracts"
```

---

### Task 5: Add ExecutionPlan and Behavior Contracts

**Files:**
- Create: `shared/protocol/execution.py`
- Create: `shared/protocol/behavior.py`
- Create: `tests/protocol/test_execution.py`
- Create: `tests/protocol/test_behavior.py`
- Modify: `shared/protocol/__init__.py`

**Interfaces:**
- Consumes: semantic target concepts only by semantic reference value; do not make execution depend on LLM internals.
- Produces:
  - `PlanOrigin`
  - `PlanValidationState`
  - `NyraResourceType`
  - `ResolvedTarget`
  - `ExecutionTarget`
  - `NyraOperation`
  - `ExecutionStep`
  - `StepStatus`
  - `ExecutionStatus`
  - `StepResult`
  - `ExecutionResult`
  - `ExecutionPlan`
  - `BehaviorLifecycle`
  - `BehaviorActionType`
  - `BehaviorTrigger`
  - `BehaviorCondition`
  - `BehaviorAction`
  - `Behavior`

- [ ] **Step 1: Write failing execution tests**

Cover:
- LLM plan can be represented as `origin=REASONING_LLM`, `validation_state=PROPOSED`;
- resolved target keeps original semantic reference;
- allowed Nyra operation vocabulary is exact;
- step dependencies refer to `step_id`;
- statuses include COMPLETED, FAILED, SKIPPED_DEPENDENCY, SKIPPED_CONDITION;
- overall result includes COMPLETED and PARTIALLY_COMPLETED;
- no rollback/on_failure/parallel_group/native HA service fields exist.

- [ ] **Step 2: Write failing behavior tests**

Cover:
- lifecycle ONE_SHOT/PERSISTENT;
- triggers are a list with OR semantics documented in model docstring;
- conditions are a list with AND semantics documented;
- actions are ordered;
- action types ACTION/DELAY/WAIT_CONDITION;
- WAIT_CONDITION timeout is optional;
- `on_timeout` defaults to STOP;
- no Home Assistant YAML/service_data/entity_id fields.

- [ ] **Step 3: Run and confirm RED**

```bash
pytest tests/protocol/test_execution.py tests/protocol/test_behavior.py -q
```

- [ ] **Step 4: Implement execution models**

Validate:
- unique `step_id` values inside a plan;
- every `depends_on` references an existing step;
- no self-dependency;
- dependency graph is acyclic.

Use a Pydantic `model_validator` on `ExecutionPlan` for graph checks.

- [ ] **Step 5: Implement Behavior models**

Behavior actions are sequential and intentionally do not expose arbitrary DAG dependencies.

`WAIT_CONDITION.on_timeout` enum values: `STOP`, `CONTINUE`; default `STOP`.

- [ ] **Step 6: Run focused tests**

```bash
pytest tests/protocol/test_execution.py tests/protocol/test_behavior.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shared/protocol/execution.py shared/protocol/behavior.py \
        shared/protocol/__init__.py tests/protocol/test_execution.py \
        tests/protocol/test_behavior.py
git commit -m "feat: add execution and behavior contracts"
```

---

### Task 6: Add Capability Foundation Contracts and Retry Semantics

**Files:**
- Create: `shared/protocol/capabilities.py`
- Create: `tests/protocol/test_capabilities.py`
- Modify: `shared/protocol/__init__.py`

**Interfaces:**
- Consumes:
  - `CorrelationContext`
  - `CommonOutcome`
  - `ErrorDetail`
  - `NyraOperation`
  - `NyraResourceType`
- Produces:
  - `CapabilityCorrelation`
  - `ResolveCardinality`
  - `ResolveStatus`
  - `ResourceReference`
  - `ResolvedResource`
  - `ResolveCandidate`
  - `ResolveResponse`
  - `ExecuteRequest`
  - `ExecuteResponse`
  - `is_idempotent_operation(operation: NyraOperation) -> bool`

- [ ] **Step 1: Write failing capability tests**

Cover:
- capability correlation does not contain `session_id`, `caller`, `user_id`, `roles`, `policy`, or auth;
- resolver ONE returns RESOLVED/AMBIGUOUS/NOT_FOUND semantics;
- candidates are Nyra resource abstractions;
- execution accepts Nyra operations/resource IDs, never raw HA service names;
- idempotency table is exact:
  - true: TURN_ON, TURN_OFF, OPEN, CLOSE, SET;
  - false: TOGGLE, INCREASE, DECREASE, TRIGGER;
- uncertain non-idempotent execution can be represented as UNKNOWN_OUTCOME.

- [ ] **Step 2: Run and confirm RED**

```bash
pytest tests/protocol/test_capabilities.py -q
```

- [ ] **Step 3: Implement capability models**

Do not add a generic `/capabilities/{name}` payload model.

Keep this task limited to common typed primitives for HA-style capabilities; actual Router HTTP endpoints and HA integration belong to the later Capability Gateway plan.

- [ ] **Step 4: Run tests**

```bash
pytest tests/protocol/test_capabilities.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/protocol/capabilities.py shared/protocol/__init__.py \
        tests/protocol/test_capabilities.py
git commit -m "feat: add capability foundation contracts"
```

---

### Task 7: Make Central Observability Reconstruct Session Correlation

**Files:**
- Modify: `router/observability.py`
- Modify: Router persistence module currently responsible for request/session lookup.
- Create: `tests/router/test_observability_correlation.py`
- Modify: `tests/router/test_request_lifecycle.py` only if helper fixtures need reuse.

**Interfaces:**
- Consumes:
  - persisted request -> session relationship;
  - log records containing request ID or origin request ID;
  - trace/span correlation.
- Produces:
  - central enrichment rule that resolves `session_id` for component records using `request_id` first, then `origin_request_id`;
  - no requirement that child components send `session_id`.

- [ ] **Step 1: Write failing distributed-correlation tests**

Build a test scenario with:
1. one session;
2. request A;
3. two traces for request A to represent clarification;
4. Router span;
5. synthetic Skills span using `request_id=A` and no session;
6. synthetic delayed job span using `origin_request_id=A`, null `request_id`, and a new trace.

Assert a session query returns all records and that each centrally persisted/enriched record is associated with the original session.

Example expected IDs:

```python
assert {row["component"] for row in session_rows} >= {"ROUTER", "SKILLS"}
assert delayed_row["origin_request_id"] == request_id
assert delayed_row["session_id"] == session_id
```

- [ ] **Step 2: Run and confirm RED**

```bash
pytest tests/router/test_observability_correlation.py -q
```

Expected: FAIL if current ingestion requires session ID on every record or does not resolve originated async work.

- [ ] **Step 3: Implement request/session enrichment**

At Router ingestion/persistence:
- if log has `request_id`, resolve session from request state;
- else if it has `origin_request_id`, resolve session from originating request;
- else leave session null;
- never trust a conflicting component-supplied session ID over Router's authoritative mapping;
- preserve trace/span IDs exactly.

Do not modify the shared logging wire protocol to require session ID.

- [ ] **Step 4: Add conflict test**

Add a test where a child log supplies a wrong session ID alongside a valid request ID. Assert Router stores/queries it under the authoritative session mapped from the request.

- [ ] **Step 5: Run observability and existing logging tests**

```bash
pytest tests/router/test_observability_correlation.py \
       tests/router -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add router/observability.py router tests/router/test_observability_correlation.py
git commit -m "feat: correlate distributed logs by request"
```

Before committing, use `git diff --name-only` and stage only the Router persistence file actually changed, not every file under `router/`.

---

### Task 8: Add Contract-Level Regression Tests and Foundation Verification

**Files:**
- Create: `tests/protocol/test_contract_invariants.py`
- Modify: `docs/state/CURRENT_STATE.md`
- Modify: `docs/ARCHITECTURE.md` if that is the existing architecture file; otherwise modify root `ARCHITECTURE.md`.
- Modify: `docs/DEPLOYMENT.md` only if current deployment docs incorrectly imply service auth or lateral first-level communication.

**Interfaces:**
- Consumes all foundation contracts.
- Produces a single regression suite documenting architectural invariants before specialist component migration begins.

- [ ] **Step 1: Write invariant tests**

`tests/protocol/test_contract_invariants.py` must verify through type fields/enums that:
- no shared correlation model requires `session_id`;
- no capability model contains `authorization`, `token`, `caller`, `roles`, or raw HA `service`;
- `SemanticResult` cannot contain a resolved HA resource;
- `ExecutionPlan` supports proposed LLM origin without being marked validated;
- manual authentication abstractions were not introduced into protocol models;
- non-idempotent operations are correctly classified.

Use model field inspection, for example:

```python
def test_capability_contract_has_no_auth_or_caller_fields():
    forbidden = {"authorization", "token", "caller", "roles"}
    assert forbidden.isdisjoint(CapabilityCorrelation.model_fields)
```

- [ ] **Step 2: Run complete protocol suite**

```bash
pytest tests/protocol -q
```

Expected: PASS.

- [ ] **Step 3: Run the complete repository test suite**

Ensure the venv has test extras installed:

```bash
python -m pip install -e ".[test]"
pytest -q
```

Expected: all tests PASS. Do not accept async-test warnings caused by a missing pytest plugin; `pytest-asyncio` must remain in test dependencies.

- [ ] **Step 4: Run static/syntax verification**

```bash
python -m compileall -q router shared tests
bash -n deploy/bootstrap/router.sh
```

Expected: both commands exit 0.

- [ ] **Step 5: Update architecture/state documentation**

Record that:
- Component Contract v1 design is approved;
- shared foundation models are implemented;
- Router consumes the shared correlation/context contracts;
- specialist services remain on alpha until their dedicated migration plans;
- no service auth exists in v1;
- no destructive CT migration occurred in this foundation step.

Do not claim Memory/Skills/LLM/Speaker-ID v1 is implemented.

- [ ] **Step 6: Run placeholder and secret scans**

```bash
grep -RInE '\b(TODO|TBD)\b' shared/protocol tests/protocol || true
grep -RInE '(api[_-]?key|authorization|bearer|password|secret)[[:space:]]*[:=][[:space:]]*["'"'"'][^*]' \
  shared/protocol router tests/protocol || true
```

Expected: no implementation placeholders and no embedded credentials.

- [ ] **Step 7: Review the diff**

```bash
git status
git diff --check
git diff --stat
```

Expected:
- no whitespace errors;
- only protocol, Router adaptation, tests, and relevant documentation are modified;
- no alpha component deletion;
- no deployment-specific addresses or credentials.

- [ ] **Step 8: Commit foundation completion**

```bash
git add shared/protocol tests/protocol router \
        tests/router/test_request_lifecycle.py \
        tests/router/test_health_ready.py \
        tests/router/test_observability_correlation.py \
        docs/state/CURRENT_STATE.md
git add ARCHITECTURE.md 2>/dev/null || true
git add docs/ARCHITECTURE.md 2>/dev/null || true
git add docs/DEPLOYMENT.md 2>/dev/null || true

git commit -m "feat: establish Component Contract v1 foundation"
```

Stage only documentation files that actually changed.

- [ ] **Step 9: Final verification after commit**

```bash
pytest -q
python -m compileall -q router shared tests
git status --short
```

Expected:
- all tests PASS;
- compileall exits 0;
- working tree clean.

---

## Out of Scope for This Plan

The following approved Component Contract v1 areas deliberately receive only shared foundation types here and must be implemented by later dedicated plans:

1. **Memory v1 implementation**
   - Operational Context persistence/resolution;
   - Semantic Memory lifecycle/search/admission;
   - memory extraction integration.

2. **Skills v1 implementation**
   - Skill registry/dispatch;
   - Semantic capability requests;
   - ExecutionPlan validation/action gate;
   - SkillJob persistence/recovery;
   - Behavior construction.

3. **LLM v1 implementation**
   - semantic/reasoning/memory-extraction endpoints;
   - provider/model abstraction;
   - read-only reasoning capability loop.

4. **Speaker-ID v1 implementation**
   - biometric engine;
   - enrollment/profile lifecycle;
   - identification diagnostics/audio TTL;
   - wake-word dataset collection/export.

5. **Capability Gateway / Home Assistant implementation**
   - real entity resolver;
   - current policy enforcement;
   - typed HA execution;
   - automation materialization/ownership.

6. **Admin extensions**
   - Session/Request diagnostic ZIP export;
   - specialist component management pages;
   - wake-word/sample UI.

These future plans MUST consume the foundation contracts instead of redefining them.
