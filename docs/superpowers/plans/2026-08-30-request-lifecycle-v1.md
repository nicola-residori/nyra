# Request Lifecycle v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Nyra Router's canonical synchronous request lifecycle, persisted clarification state, authoritative session closure, identity outcomes, interaction-state events, and recoverable WebSocket event channel.

**Architecture:** Extend the existing FastAPI Router without migrating production Skills, Memory, Voice, or Home Assistant. Shared Pydantic models define the wire contract; Router creates traces and owns lifecycle state in SQLite; focused lifecycle modules handle identity, request persistence, state publication, and orchestration; `/v1/events` provides an ephemeral event stream with explicit resynchronization.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLite WAL, asyncio, pytest, FastAPI/Starlette TestClient, existing Nyra observability protocol/client.

**Spec:** `docs/superpowers/specs/2026-08-30-request-lifecycle-v1-design.md`

## Global Constraints

- Repository code, comments, documentation, API names, technical log events, commit messages, and test data are English.
- `session_id`, `request_id`, and `trace_id` are UUIDs; `span_id` remains `CT#operation#random`.
- Trusted ingress creates session/request UUIDs; Router creates trace UUIDs.
- Clarification follow-ups reuse session/request UUIDs and get a new trace UUID.
- `closed` is authoritative: the ingress MUST NOT open or resume follow-up.
- Jobs have null session/request UUIDs and may carry `origin_request_id`.
- Router owns Speaker-ID initiation for `ha_speaker`; Home Assistant must not perform it for Router.
- Router owns context, policy, routing, request state, and processing interaction states.
- Home Assistant owns physical `IDLE`, `LISTENING`, and `SPEAKING` states.
- Application request state is stored separately from observability logs.
- WebSocket connections are ephemeral and recoverable; clients reconnect, re-authenticate, re-subscribe, and resynchronize.
- No service addresses, installation-specific names, or credentials are hardcoded.
- Configuration precedence remains `ENV -> config.yaml -> defaults`.
- This milestone must not migrate production Skills, Memory, Voice, or the Home Assistant adapter.

---

## File Structure

```text
shared/protocol/requests.py       Request/response, source and identity wire contracts
shared/protocol/events.py         Interaction-state and event wire contracts

router/lifecycle/__init__.py
router/lifecycle/models.py        Persisted request-state domain model
router/lifecycle/store.py         Request-state SQLite persistence
router/lifecycle/identity.py      Identity outcome comparison
router/lifecycle/events.py        State registry and async event broker
router/lifecycle/service.py       Request lifecycle orchestration

router/api/requests.py            POST /v1/requests
router/api/events.py              WS /v1/events and state resync
router/main.py                    Register lifecycle APIs

tests/protocol/test_requests.py
tests/protocol/test_events.py
tests/router/test_request_store.py
tests/router/test_identity.py
tests/router/test_event_broker.py
tests/router/test_request_lifecycle.py
tests/router/test_request_api.py
tests/router/test_event_api.py
```

Keep existing observability persistence in `router/storage/sqlite.py`; lifecycle application state must not be reconstructed from logs.

---

### Task 1: Request Wire Protocol

**Files:**
- Create: `shared/protocol/requests.py`
- Create: `tests/protocol/test_requests.py`

**Interfaces:**
- Produces `ExecutionType`, `RequestStatus`, `CloseReason`, `RequestSource`, `TrustedIdentity`, `RequestInput`, `NyraRequest`, `NyraResponseBody`, `NyraRequestResponse`.
- UUID-bearing fields use `UUID | None`.

- [ ] **Step 1: Write failing tests**

Add tests equivalent to:

```python
def test_ha_speaker_requires_session_and_request_ids(): ...
def test_ha_speaker_accepts_source_without_identity(): ...
def test_ha_assist_accepts_trusted_identity(): ...
def test_job_requires_null_session_and_request_ids(): ...
def test_job_accepts_origin_request_id(): ...
def test_unknown_execution_type_is_rejected(): ...
def test_invalid_uuid_is_rejected(): ...
def test_closed_response_accepts_close_reason_and_null_body(): ...
```

- [ ] **Step 2: Verify RED**

```bash
pytest tests/protocol/test_requests.py -v
```

Expected: import failure because `shared.protocol.requests` does not exist.

- [ ] **Step 3: Implement minimal protocol**

```python
class ExecutionType(str, Enum):
    HA_SPEAKER = "ha_speaker"
    HA_ASSIST = "ha_assist"
    JOB = "job"
    NYRA_UI = "nyra_ui"

class RequestStatus(str, Enum):
    COMPLETED = "completed"
    NEEDS_CLARIFICATION = "needs_clarification"
    CLOSED = "closed"
    FAILED = "failed"
    EXPIRED = "expired"

class CloseReason(str, Enum):
    EXPLICIT_CLOSE = "explicit_close"
    DIRECT_COMMAND = "direct_command"
    ALARM_DISMISSED = "alarm_dismissed"
    TIMEOUT = "timeout"
    POLICY = "policy"
```

Validation rules:
- non-job ingress requires `session_id` and `request_id`;
- jobs require both to be null;
- `origin_request_id` is allowed for jobs;
- `close_reason` is required when response status is `closed` and otherwise null.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/protocol/test_requests.py -v
```

- [ ] **Step 5: Commit**

```bash
git add shared/protocol/requests.py tests/protocol/test_requests.py
git commit -m "feat: define request lifecycle protocol"
```

---

### Task 2: Interaction Event Protocol

**Files:**
- Create: `shared/protocol/events.py`
- Create: `tests/protocol/test_events.py`

**Interfaces:**
- Produces `InteractionState`, `EventCategory`, `InteractionStateChanged`, `SessionClosedEvent`, `EventSubscription`, `StateSnapshot`.

- [ ] **Step 1: Write failing tests**

Cover all state values, serialization, optional source, correlation IDs, `SESSION_CLOSED`, close reason, subscription parsing, and snapshot serialization.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/protocol/test_events.py -v
```

- [ ] **Step 3: Implement event contracts**

Define:

```python
class InteractionState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    SPEAKING = "SPEAKING"
    PROCESSING = "PROCESSING"
    IDENTIFYING = "IDENTIFYING"
    MEMORY = "MEMORY"
    SKILL_CHECK = "SKILL_CHECK"
    SKILL_EXECUTION = "SKILL_EXECUTION"
    LLM_REASONING = "LLM_REASONING"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    ERROR = "ERROR"
```

Use stable event names `INTERACTION_STATE_CHANGED` and `SESSION_CLOSED`.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/protocol/test_events.py -v
```

- [ ] **Step 5: Commit**

```bash
git add shared/protocol/events.py tests/protocol/test_events.py
git commit -m "feat: define router event protocol"
```

---

### Task 3: Persistent Request State

**Files:**
- Create: `router/lifecycle/__init__.py`
- Create: `router/lifecycle/models.py`
- Create: `router/lifecycle/store.py`
- Create: `tests/router/test_request_store.py`

**Interfaces:**
- Produces:

```python
class RequestStateStore:
    def create(self, state: PersistedRequestState) -> None: ...
    def get(self, request_id: UUID) -> PersistedRequestState | None: ...
    def update(self, state: PersistedRequestState) -> None: ...
    def expire_due(self, now: datetime) -> int: ...
```

`PersistedRequestState` contains request/session UUIDs, type, language, source, identity, original input, status, current trace UUID, pending state, timestamps, and optional expiration.

- [ ] **Step 1: Write failing store tests**

Cover create/get, update, JSON round-trip, current identity update, pending-state persistence, and expiration.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/router/test_request_store.py -v
```

- [ ] **Step 3: Implement SQLite storage**

Create a dedicated `request_states` table. Store timestamps in UTC and structured values as JSON. Default clarification expiry is configured as 120 seconds rather than embedded in request logic.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/router/test_request_store.py -v
```

- [ ] **Step 5: Commit**

```bash
git add router/lifecycle tests/router/test_request_store.py
git commit -m "feat: persist router request state"
```

---

### Task 4: Identity Outcome Semantics

**Files:**
- Create: `router/lifecycle/identity.py`
- Create: `tests/router/test_identity.py`

**Interfaces:**
- Produces:

```python
class IdentityOutcome(str, Enum):
    IDENTIFIED = "IDENTITY_IDENTIFIED"
    CONFIRMED = "IDENTITY_CONFIRMED"
    CHANGED = "IDENTITY_CHANGED"
    GUEST = "IDENTITY_GUEST"

def resolve_identity_outcome(
    previous_user_id: str | None,
    detected_user_id: str | None,
) -> IdentityResolution: ...
```

- [ ] **Step 1: Write failing tests**

Test:
- null -> `user-a` => IDENTIFIED
- `user-a` -> `user-a` => CONFIRMED
- `user-a` -> `user-b` => CHANGED
- accepted detection absent => GUEST with current ID `guest`

- [ ] **Step 2: Verify RED**

```bash
pytest tests/router/test_identity.py -v
```

- [ ] **Step 3: Implement pure identity comparison**

Do not implement Speaker-ID transport here. This module consumes an accepted SID result and determines Router semantics.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/router/test_identity.py -v
```

- [ ] **Step 5: Commit**

```bash
git add router/lifecycle/identity.py tests/router/test_identity.py
git commit -m "feat: add identity outcome semantics"
```

---

### Task 5: Interaction-State Registry and Event Broker

**Files:**
- Create: `router/lifecycle/events.py`
- Create: `tests/router/test_event_broker.py`

**Interfaces:**
- Produces:

```python
class InteractionEventBroker:
    async def publish_state(self, event: InteractionStateChanged) -> None: ...
    async def publish_session_closed(self, event: SessionClosedEvent) -> None: ...
    async def subscribe(self, categories: set[EventCategory]) -> Subscription: ...
    async def unsubscribe(self, subscription: Subscription) -> None: ...
    def snapshot(self, source_id: str | None = None) -> list[StateSnapshot]: ...
```

- [ ] **Step 1: Write failing broker tests**

Verify publication, category filtering, current state retained by source, snapshot recovery after a missed event, unsubscribe, and bounded subscriber queues so a dead client cannot block Router.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/router/test_event_broker.py -v
```

- [ ] **Step 3: Implement async broker**

Use per-subscriber bounded `asyncio.Queue`. On overflow, disconnect/drop the unhealthy subscriber rather than blocking the request path. Keep only current state for resynchronization; do not build replay storage.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/router/test_event_broker.py -v
```

- [ ] **Step 5: Commit**

```bash
git add router/lifecycle/events.py tests/router/test_event_broker.py
git commit -m "feat: add interaction event broker"
```

---

### Task 6: Lifecycle Orchestrator Skeleton

**Files:**
- Create: `router/lifecycle/service.py`
- Create: `tests/router/test_request_lifecycle.py`

**Interfaces:**
- Produces:

```python
class RequestLifecycleService:
    async def execute(self, request: NyraRequest) -> NyraRequestResponse: ...
```

Dependencies are injected: request store, event broker, logger, clock, trace UUID factory, and placeholder ports for later SID/context/skill/LLM integrations.

- [ ] **Step 1: Write failing lifecycle tests**

Test:
- Router generates a new trace UUID;
- ingress session/request UUIDs are preserved;
- first request state is persisted;
- a second independent request receives its own state;
- job execution has no session/request state record;
- Router publishes `PROCESSING` for a normal stub execution.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/router/test_request_lifecycle.py -v
```

- [ ] **Step 3: Implement minimal orchestrator**

The milestone must not call production Skills/Memory/Voice yet. Use explicit injected no-op/stub decision ports so the lifecycle foundation is independently testable.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/router/test_request_lifecycle.py -v
```

- [ ] **Step 5: Commit**

```bash
git add router/lifecycle/service.py tests/router/test_request_lifecycle.py
git commit -m "feat: add router request lifecycle"
```

---

### Task 7: Clarification Continuation

**Files:**
- Modify: `router/lifecycle/service.py`
- Modify: `router/lifecycle/store.py`
- Modify: `tests/router/test_request_lifecycle.py`

**Interfaces:**
- `RequestLifecycleService.execute()` recognizes an existing `request_id` in `needs_clarification`, validates session ownership, creates a new trace, loads pending state, and resumes it.

- [ ] **Step 1: Add failing clarification tests**

Verify:
- first trace returns `needs_clarification`;
- persisted status/pending state are present;
- follow-up keeps session/request UUIDs;
- follow-up gets a different trace UUID;
- mismatched session UUID is rejected;
- expired pending request returns/raises the explicit expired outcome;
- completed requests cannot be silently resumed as clarification.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/router/test_request_lifecycle.py -k clarification -v
```

- [ ] **Step 3: Implement continuation logic**

Keep semantic pending state opaque to ingress. Expire pending requests using configured timeout and UTC clock dependency.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/router/test_request_lifecycle.py -k clarification -v
```

- [ ] **Step 5: Commit**

```bash
git add router/lifecycle/service.py router/lifecycle/store.py tests/router/test_request_lifecycle.py
git commit -m "feat: support clarification continuations"
```

---

### Task 8: Authoritative Session Closure

**Files:**
- Modify: `router/lifecycle/service.py`
- Modify: `tests/router/test_request_lifecycle.py`

**Interfaces:**
- A lifecycle decision can return `RequestStatus.CLOSED` plus `CloseReason`.
- Service publishes `SESSION_CLOSED`.
- Closed request state cannot be resumed.

- [ ] **Step 1: Add failing closure tests**

Test:
- direct command returns `closed` + `direct_command`;
- explicit close returns `closed` + `explicit_close`;
- alarm dismissal can return `closed` + `alarm_dismissed` with null response body;
- `SESSION_CLOSED` contains correlation IDs and reason;
- a closed request cannot accept a clarification continuation.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/router/test_request_lifecycle.py -k "closed or alarm or close" -v
```

- [ ] **Step 3: Implement closure semantics**

Closure is a Router lifecycle result, not an HA-specific workaround. Publish the event after request state is atomically updated to `closed`.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/router/test_request_lifecycle.py -k "closed or alarm or close" -v
```

- [ ] **Step 5: Commit**

```bash
git add router/lifecycle/service.py tests/router/test_request_lifecycle.py
git commit -m "feat: add authoritative session closure"
```

---

### Task 9: Identity Integration Boundary

**Files:**
- Modify: `router/lifecycle/service.py`
- Modify: `tests/router/test_request_lifecycle.py`

**Interfaces:**
- Define an injected async Speaker-ID port:

```python
class SpeakerIdentityPort(Protocol):
    async def identify(self, request: NyraRequest, trace_id: UUID) -> str | None: ...
```

- [ ] **Step 1: Add failing integration tests**

Verify:
- `ha_speaker` starts SID through Router;
- `ha_assist` does not call SID when trusted identity is supplied;
- `IDENTIFYING` is published for speaker requests;
- IDENTIFIED/CONFIRMED/CHANGED/GUEST outcomes update persisted current identity;
- identity-independent work is not structurally forced behind SID.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/router/test_request_lifecycle.py -k identity -v
```

- [ ] **Step 3: Implement boundary and concurrency**

Use an asyncio task for SID so later context/routing work can run concurrently where identity is not required. Do not add the production Voice HTTP client in this milestone.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/router/test_request_lifecycle.py -k identity -v
```

- [ ] **Step 5: Commit**

```bash
git add router/lifecycle/service.py tests/router/test_request_lifecycle.py
git commit -m "feat: integrate router identity lifecycle"
```

---

### Task 10: Memory and Skill State Boundaries

**Files:**
- Modify: `router/lifecycle/service.py`
- Modify: `tests/router/test_request_lifecycle.py`

**Interfaces:**
- Add injectable ports for context resolution, optional semantic memory, skill matching/execution, and LLM fallback.
- No production network clients are added.

- [ ] **Step 1: Add failing routing-state tests**

Verify logical publication paths:

```text
PROCESSING -> MEMORY -> SKILL_CHECK -> SKILL_EXECUTION
PROCESSING -> MEMORY -> SKILL_CHECK -> LLM_REASONING
```

Also verify semantic Memory search can be skipped while operational context resolution still occurs.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/router/test_request_lifecycle.py -k "memory or skill or llm" -v
```

- [ ] **Step 3: Implement orchestration ports**

Keep Router as owner of the ordering and state publication. Service adapters added in later migration milestones will implement these ports.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/router/test_request_lifecycle.py -k "memory or skill or llm" -v
```

- [ ] **Step 5: Commit**

```bash
git add router/lifecycle/service.py tests/router/test_request_lifecycle.py
git commit -m "feat: add routing lifecycle boundaries"
```

---

### Task 11: Expose `POST /v1/requests`

**Files:**
- Create: `router/api/requests.py`
- Modify: `router/main.py`
- Create: `tests/router/test_request_api.py`

**Interfaces:**
- `POST /v1/requests` consumes `NyraRequest` and returns `NyraRequestResponse`.
- API dependency wiring supplies the lifecycle service.

- [ ] **Step 1: Write failing API tests**

Cover valid HA speaker/Assist requests, invalid UUIDs, invalid job IDs, completed response, clarification response, closed response, and response trace UUID.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/router/test_request_api.py -v
```

- [ ] **Step 3: Implement API and register router**

Keep endpoint thin: validation and lifecycle delegation only.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/router/test_request_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git add router/api/requests.py router/main.py tests/router/test_request_api.py
git commit -m "feat: expose router request endpoint"
```

---

### Task 12: Expose Recoverable `WS /v1/events`

**Files:**
- Create: `router/api/events.py`
- Modify: `router/main.py`
- Create: `tests/router/test_event_api.py`

**Interfaces:**
- WebSocket accepts authenticated clients according to the existing Router auth mechanism.
- Client sends a subscription message specifying categories.
- Server sends subscribed events and supports a current-state snapshot/resync operation.
- Heartbeat is supported at application or framework level and documented by the protocol tests.

- [ ] **Step 1: Write failing WebSocket tests**

Cover connect, authentication rejection, subscribe, receive interaction event, category filtering, disconnect cleanup, reconnect, re-subscribe, and state resync without replay.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/router/test_event_api.py -v
```

- [ ] **Step 3: Implement WebSocket endpoint**

Do not persist missed events. On resync, return current state snapshots from the broker.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/router/test_event_api.py -v
```

- [ ] **Step 5: Commit**

```bash
git add router/api/events.py router/main.py tests/router/test_event_api.py
git commit -m "feat: expose router event websocket"
```

---

### Task 13: Lifecycle Observability

**Files:**
- Modify: `router/lifecycle/service.py`
- Modify: `router/api/events.py`
- Modify: `tests/router/test_request_lifecycle.py`
- Modify: `tests/router/test_event_api.py`

**Interfaces:**
- Reuse existing Nyra structured logging contract.
- Each lifecycle operation uses a stable span ID and paired REQUEST/RESPONSE or REQUEST/FAULT.
- Stable events include identity outcomes, interaction-state changes, `SESSION_CLOSED`, WebSocket connect/disconnect/subscription/resync.

- [ ] **Step 1: Add failing observability tests**

Assert correlation fields, stable English event names, same-span lifecycle pairing, close reason, and absence of secrets.

- [ ] **Step 2: Verify RED**

```bash
pytest tests/router/test_request_lifecycle.py tests/router/test_event_api.py -k observability -v
```

- [ ] **Step 3: Add lifecycle logging**

Do not block the request path on remote log delivery; use the existing asynchronous logger behavior.

- [ ] **Step 4: Verify GREEN**

```bash
pytest tests/router/test_request_lifecycle.py tests/router/test_event_api.py -k observability -v
```

- [ ] **Step 5: Commit**

```bash
git add router/lifecycle/service.py router/api/events.py tests/router
git commit -m "feat: trace request lifecycle operations"
```

---

### Task 14: Configuration and Bootstrap Compatibility

**Files:**
- Modify: `.env.example`
- Modify: deployment/bootstrap configuration only if a new setting is required
- Create or modify: lifecycle configuration tests in the established config test location

**Interfaces:**
- Add configuration for clarification timeout and WebSocket queue/heartbeat values using existing configuration precedence.
- No addresses or credentials are introduced as defaults.

- [ ] **Step 1: Add failing config tests**

Verify default clarification timeout = 120 seconds and environment override behavior.

- [ ] **Step 2: Verify RED**

Run the project's config-focused tests plus:

```bash
pytest -v
```

- [ ] **Step 3: Implement configuration**

Document environment variable names in `.env.example`; preserve `ENV -> config.yaml -> defaults`.

- [ ] **Step 4: Verify GREEN**

```bash
pytest -v
```

- [ ] **Step 5: Commit**

```bash
git add .env.example router tests deploy
git commit -m "config: add request lifecycle settings"
```

---

### Task 15: Full Verification and Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-08-30-request-lifecycle-v1-design.md` only if implementation exposed a verified non-semantic clarification
- Modify: `docs/state/CURRENT_STATE.md` if present
- Modify: relevant API/deployment documentation if present

**Interfaces:**
- No new runtime interface; this task verifies the completed milestone and records current state.

- [ ] **Step 1: Run complete tests**

```bash
pytest -v
```

Expected: all existing and new tests pass.

- [ ] **Step 2: Compile Python**

```bash
python -m compileall router shared tests
```

Expected: exit code 0.

- [ ] **Step 3: Validate bootstrap shell syntax**

```bash
bash -n deploy/bootstrap/router.sh
```

Expected: exit code 0.

- [ ] **Step 4: Run focused lifecycle tests again**

```bash
pytest \
  tests/protocol/test_requests.py \
  tests/protocol/test_events.py \
  tests/router/test_request_store.py \
  tests/router/test_identity.py \
  tests/router/test_event_broker.py \
  tests/router/test_request_lifecycle.py \
  tests/router/test_request_api.py \
  tests/router/test_event_api.py -v
```

Expected: all pass.

- [ ] **Step 5: Update current-state documentation**

Record that Request Lifecycle v1 foundation is implemented, but production Skills/Memory/Voice/HA migration remains pending.

- [ ] **Step 6: Review repository diff**

```bash
git status
git diff --check
git diff --stat
```

Expected: no whitespace errors or unintended files.

- [ ] **Step 7: Commit verification/docs**

```bash
git add docs
git commit -m "docs: record request lifecycle v1 state"
```

Do not claim the milestone complete unless the fresh verification commands above pass.

---

## Self-Review

### Spec coverage
- Synchronous `/v1/requests`: Tasks 6, 11.
- UUID ownership and clarification trace semantics: Tasks 1, 3, 6, 7.
- Jobs and `origin_request_id`: Tasks 1, 6.
- Identity outcomes and Router-owned SID initiation: Tasks 4, 9.
- Request persistence and expiry: Tasks 3, 7, 14.
- `closed`, close reasons, alarm dismissal, `SESSION_CLOSED`, no-follow-up semantics: Tasks 1, 2, 8, 13.
- Interaction states: Tasks 2, 5, 6, 10.
- Memory/Skill state boundaries: Task 10.
- Persistent WebSocket, subscription, reconnect/resync support: Tasks 5, 12.
- Observability: Task 13.
- Configuration/reproducibility: Task 14.
- Final verification: Task 15.

### Placeholder scan
No unresolved placeholders or unspecified implementation steps are intentionally present. Production service migrations are explicitly outside this milestone.

### Type consistency
Protocol enums and lifecycle interfaces use the same names throughout this plan. UUID ownership and `closed` semantics match the approved design spec.
