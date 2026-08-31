# Home Assistant Adapter Milestone 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the definitive thin Home Assistant Nyra conversation adapter, using the existing Router request lifecycle and WebSocket event stream, with correlated real-time speaker feedback and no legacy fallback.

**Architecture:** Home Assistant owns ingress `session_id` / `request_id`, sends requests to `POST /v1/requests`, and consumes Router events from `WS /v1/events`. Router remains the orchestrator and emits semantic states; the HA speaker bridge converts them into speaker commands. HA-specific modules stay thin, while session management, Router client parsing, and speaker rendering state are isolated in testable modules.

**Tech Stack:** Python 3.11+, Home Assistant custom integration APIs, `httpx`, asyncio/WebSocket client support available in Home Assistant runtime, Pydantic v2 shared contracts, pytest/pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-08-31-home-assistant-adapter-design.md`

## Global Constraints

- No legacy/parallel Home Assistant Nyra path.
- Home Assistant remains a thin adapter; Router remains central orchestrator.
- HA adapter generates ingress `session_id` and `request_id`; Router generates `trace_id`.
- Use existing `POST /v1/requests`; do not introduce a duplicate HA execution endpoint.
- Use existing `WS /v1/events` for live Router-to-HA events; do not poll observability storage.
- Source/device never implies personal identity.
- `ha_assist` may carry authoritative HA identity; `ha_speaker` must not invent identity.
- Listening/transcribing/clarification render as fast pulsing white.
- Speaking renders as audio-reactive purple, including Job speech.
- Wake-word success plays the opening sound locally before Router round-trip/listening feedback.
- Session close plays closing sound + blue blink, then idle.
- Local processing = turquoise comet; global processing = rainbow comet; tool use = yellow comet.
- Identification = warm-white comet followed by exactly two result blinks.
- No general visual `WAITING` state for deferred Jobs/Behaviors.
- Live speaker feedback must be correlated and isolated by source/device/session.
- No blind conversational retry.
- No new mTLS/service-identity scheme in Component Contract v1.

---

### Task 1: Normalize Shared Speaker/Event Contracts

**Files:**
- Modify: `shared/protocol/events.py`
- Modify: `shared/protocol/__init__.py`
- Test: `tests/protocol/test_events.py`

**Interfaces:**
- Produces `InteractionState` values needed by speaker rendering: `IDLE`, `LISTENING`, `TRANSCRIBING`, `IDENTIFYING`, `PROCESSING_LOCAL`, `PROCESSING_GLOBAL`, `USING_TOOL`, `WAITING_CLARIFICATION`, `SPEAKING`, `ERROR`.
- Produces transient `IdentityFeedback` values `RECOGNIZED`, `NOT_RECOGNIZED`, `IDENTITY_CHANGED`.
- Produces a correlated identity-result event and preserves existing `SessionClosedEvent`.
- Keeps `EventCategory` subscription-compatible with `WS /v1/events`.

- [ ] **Step 1: Write failing protocol tests**

Add tests asserting exact enum vocabularies, correlation validation, source routing, and identity-result serialization.

Example assertions:

```python
def test_interaction_state_has_speaker_contract_v1():
    assert {x.value for x in InteractionState} == {
        "IDLE",
        "LISTENING",
        "TRANSCRIBING",
        "IDENTIFYING",
        "PROCESSING_LOCAL",
        "PROCESSING_GLOBAL",
        "USING_TOOL",
        "WAITING_CLARIFICATION",
        "SPEAKING",
        "ERROR",
    }

def test_identity_feedback_event_is_correlated():
    event = IdentityFeedbackEvent(
        feedback=IdentityFeedback.IDENTITY_CHANGED,
        source=RequestSource(id="nyra-soggiorno", area="soggiorno"),
        session_id=new_session_id(),
        request_id=new_request_id(),
        trace_id=new_trace_id(),
    )
    assert event.event == "IDENTITY_FEEDBACK"
    assert event.source.id == "nyra-soggiorno"
```

- [ ] **Step 2: Run protocol tests and verify RED**

Run:

```bash
pytest -q tests/protocol/test_events.py
```

Expected: failures because the new state vocabulary/event types do not yet exist.

- [ ] **Step 3: Implement the minimal shared event contract**

Update `shared/protocol/events.py` so semantic speaker states replace implementation-specific visual states such as `MEMORY`, `SKILL_CHECK`, `SKILL_EXECUTION`, and `LLM_REASONING`.

Keep event payloads semantic; do not add RGB values, animation names, sound filenames, or Home Assistant service calls.

Add the identity feedback event as a transient event rather than a persistent interaction state.

- [ ] **Step 4: Export stable types**

Expose the new event types through `shared/protocol/__init__.py` following existing explicit-export style.

- [ ] **Step 5: Run protocol tests GREEN**

```bash
pytest -q tests/protocol/test_events.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shared/protocol/events.py shared/protocol/__init__.py tests/protocol/test_events.py
git commit -m "feat: define speaker interaction event contract"
```

---

### Task 2: Adapt Router Lifecycle Events to the Semantic Speaker Contract

**Files:**
- Modify: `router/lifecycle/service.py`
- Modify: `router/lifecycle/events.py`
- Modify: `router/lifecycle/identity.py` only if mapping helpers are useful
- Test: `tests/router/test_event_broker.py`
- Test: `tests/router/test_request_lifecycle.py`
- Test: `tests/router/test_event_api.py`

**Interfaces:**
- Consumes Task 1 `InteractionState` and identity feedback event.
- Router publishes `PROCESSING_LOCAL` while on the local/context/skill route.
- Router publishes `PROCESSING_GLOBAL` when reasoning LLM is entered.
- Router publishes `IDENTIFYING` for speaker identity resolution.
- Router publishes identity feedback after identity resolution.
- Router publishes `WAITING_CLARIFICATION` for clarification.
- Existing `SESSION_CLOSED` remains authoritative for closing feedback.
- `USING_TOOL`, `LISTENING`, `TRANSCRIBING`, and `SPEAKING` are legal protocol states but are emitted only by the component that actually owns those live transitions; do not fabricate them in Router lifecycle code.

- [ ] **Step 1: Write failing lifecycle/event tests**

Add tests for:

```text
ha_speaker:
PROCESSING_LOCAL
IDENTIFYING
identity feedback
PROCESSING_LOCAL
... skill path ...

LLM fallback:
PROCESSING_LOCAL
...
PROCESSING_GLOBAL

clarification:
...
WAITING_CLARIFICATION
```

Also assert that old implementation-detail states (`MEMORY`, `SKILL_CHECK`, `SKILL_EXECUTION`, `LLM_REASONING`, generic `PROCESSING`) are not emitted.

Test identity mapping:

```text
detected first known user     -> RECOGNIZED
same known user as previous   -> RECOGNIZED
different known user          -> IDENTITY_CHANGED
no recognized user            -> NOT_RECOGNIZED
```

- [ ] **Step 2: Run focused Router tests RED**

```bash
pytest -q \
  tests/router/test_event_broker.py \
  tests/router/test_request_lifecycle.py \
  tests/router/test_event_api.py
```

Expected: failures against old event vocabulary/order.

- [ ] **Step 3: Implement Router semantic transitions**

In `RequestLifecycleService`, replace implementation-detail interaction-state emission with semantic route-level states.

Do not emit a fake `USING_TOOL`: that state is reserved for actual future/current tool invocation boundaries.

After speaker identity resolves, publish the transient correlated identity feedback event in addition to observability logging.

- [ ] **Step 4: Extend broker/subscriptions only as required**

Ensure the current broker and `WS /v1/events` can publish/subscribe/serialize the new identity feedback category/event while preserving heartbeat, authentication, subscription, and resync behavior.

Persistent state snapshots should track long-lived interaction states, not transient identity blink events.

- [ ] **Step 5: Run focused tests GREEN**

```bash
pytest -q \
  tests/router/test_event_broker.py \
  tests/router/test_request_lifecycle.py \
  tests/router/test_event_api.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add router/lifecycle/service.py router/lifecycle/events.py router/lifecycle/identity.py \
  tests/router/test_event_broker.py tests/router/test_request_lifecycle.py tests/router/test_event_api.py
git commit -m "feat: publish semantic speaker pipeline events"
```

---

### Task 3: Build the Pure Runtime Session Manager

**Files:**
- Create: `homeassistant/custom_components/nyra/session.py`
- Create: `tests/homeassistant/test_session.py`

**Interfaces:**
- Produces `SessionManager`.
- `get_or_create_session(conversation_key: str) -> str`
- `get_request_id(conversation_key: str) -> str`
- `preserve_request(conversation_key: str) -> None`
- `complete_request(conversation_key: str) -> None`
- `close_session(conversation_key: str) -> None`
- `expire() -> None`
- IDs use shared protocol generators/validators.

The exact method names may be adjusted once implementation starts, but all behaviors below must remain explicit and test-covered.

- [ ] **Step 1: Write failing session tests**

Cover:

```python
def test_same_conversation_reuses_session():
    ...

def test_terminal_request_gets_new_request_next_turn():
    ...

def test_clarification_preserves_request():
    ...

def test_expired_conversation_gets_new_session():
    ...
```

Use an injected clock so expiration is deterministic.

- [ ] **Step 2: Run test RED**

```bash
pytest -q tests/homeassistant/test_session.py
```

Expected: import/module failure.

- [ ] **Step 3: Implement minimal runtime manager**

Store only:

```text
conversation_key
session_id
active_request_id
last_activity
```

No semantic conversation state, database, HA entity resolution, identity inference, or Router policy.

- [ ] **Step 4: Run test GREEN**

```bash
pytest -q tests/homeassistant/test_session.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add homeassistant/custom_components/nyra/session.py tests/homeassistant/test_session.py
git commit -m "feat: add Home Assistant Nyra session manager"
```

---

### Task 4: Build and Test the Router HTTP Client

**Files:**
- Create: `homeassistant/custom_components/nyra/client.py`
- Create: `homeassistant/custom_components/nyra/const.py`
- Test: `tests/homeassistant/test_client.py`

**Interfaces:**
- Produces `NyraRouterClient`.
- `async_ready() -> bool` validates `/ready`.
- `async_execute(request: NyraRequest) -> NyraRequestResponse` performs exactly one `POST /v1/requests`.
- Optional bearer token uses the existing Router ingress-token convention.
- Defines explicit adapter exceptions for unavailable, contract/request rejection, and invalid response.

- [ ] **Step 1: Write failing HTTP client tests**

Using `httpx.MockTransport`, cover:

- `/ready` READY;
- `/ready` not ready;
- authorization header when token configured;
- exact `POST /v1/requests` path;
- serialization of `NyraRequest`;
- validation of `NyraRequestResponse`;
- timeout/connection error;
- Router 4xx;
- Router 5xx;
- malformed response;
- exactly one request attempt on timeout/error.

- [ ] **Step 2: Run client tests RED**

```bash
pytest -q tests/homeassistant/test_client.py
```

Expected: import/module failure.

- [ ] **Step 3: Implement client**

Use the existing shared request/response models directly rather than duplicating wire DTOs.

Do not retry inside `async_execute`.

- [ ] **Step 4: Run client tests GREEN**

```bash
pytest -q tests/homeassistant/test_client.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add homeassistant/custom_components/nyra/client.py \
  homeassistant/custom_components/nyra/const.py \
  tests/homeassistant/test_client.py
git commit -m "feat: add Home Assistant Router client"
```

---

### Task 5: Build the Speaker Rendering State Machine

**Files:**
- Create: `homeassistant/custom_components/nyra/speaker.py`
- Create: `tests/homeassistant/test_speaker.py`

**Interfaces:**
- Consumes semantic Router events.
- Produces abstract speaker-output commands; hardware/ESPHome details stay behind a narrow port/protocol.
- Maintains per-speaker current processing state so temporary `USING_TOOL` can restore the preceding local/global rendering.
- Accepts session-close and transient identity-feedback events.
- Allows `SPEAKING` without requiring a listening session.

Suggested testable output protocol:

```python
class SpeakerOutputPort(Protocol):
    async def set_idle(self, source_id: str) -> None: ...
    async def pulse_white_fast(self, source_id: str) -> None: ...
    async def comet_warm_white(self, source_id: str) -> None: ...
    async def blink_identity(self, source_id: str, feedback: IdentityFeedback, count: int) -> None: ...
    async def comet_turquoise(self, source_id: str) -> None: ...
    async def comet_rainbow(self, source_id: str) -> None: ...
    async def comet_yellow(self, source_id: str) -> None: ...
    async def speaking_purple(self, source_id: str) -> None: ...
    async def error_red(self, source_id: str) -> None: ...
    async def close_feedback(self, source_id: str) -> None: ...
```

Audio-reactive brightness itself may be implemented by ESPHome/speaker firmware; the HA contract is to select the `speaking_purple` effect/state.

- [ ] **Step 1: Write failing rendering tests**

Cover every approved mapping and:

```text
PROCESSING_GLOBAL -> USING_TOOL -> PROCESSING_GLOBAL
PROCESSING_LOCAL  -> USING_TOOL -> PROCESSING_LOCAL
WAITING_CLARIFICATION -> same output as LISTENING
identity feedback -> exactly count=2
SESSION_CLOSED -> close_feedback -> idle
Job SPEAKING -> speaking_purple without session open/listening
no generic WAITING state exists
```

- [ ] **Step 2: Run speaker tests RED**

```bash
pytest -q tests/homeassistant/test_speaker.py
```

Expected: import/module failure.

- [ ] **Step 3: Implement state machine**

Keep state keyed by source/speaker ID. Ignore events lacking sufficient routing information rather than broadcasting them to every speaker.

- [ ] **Step 4: Add concurrent-speaker isolation tests**

Simulate two source IDs with interleaved events and verify commands never cross target IDs.

- [ ] **Step 5: Run speaker tests GREEN**

```bash
pytest -q tests/homeassistant/test_speaker.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add homeassistant/custom_components/nyra/speaker.py tests/homeassistant/test_speaker.py
git commit -m "feat: add Nyra speaker feedback state machine"
```

---

### Task 6: Build the Router WebSocket Event Client

**Files:**
- Create: `homeassistant/custom_components/nyra/events.py`
- Modify: `homeassistant/custom_components/nyra/__init__.py` if runtime wiring is needed
- Test: `tests/homeassistant/test_events.py`

**Interfaces:**
- Connects to existing `WS /v1/events`.
- Authenticates using existing bearer token convention.
- Subscribes to required event categories.
- Parses shared protocol events.
- Dispatches speaker-relevant events to `SpeakerStateMachine`.
- Responds to reconnect by requesting `resync` for relevant source state.
- Does not use observability database/log polling for live state.

- [ ] **Step 1: Write failing event-client tests**

Use a fake WebSocket transport/session abstraction to cover:

- bearer auth;
- subscribe message;
- interaction state dispatch;
- identity feedback dispatch;
- session close dispatch;
- ping/pong;
- reconnect-compatible resync;
- malformed event ignored/logged without killing the integration;
- event for speaker A never dispatched as speaker B.

- [ ] **Step 2: Run tests RED**

```bash
pytest -q tests/homeassistant/test_events.py
```

Expected: import/module failure.

- [ ] **Step 3: Implement the event client**

Keep transport implementation separate enough that tests do not require a live Router or physical Home Assistant instance.

- [ ] **Step 4: Run tests GREEN**

```bash
pytest -q tests/homeassistant/test_events.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add homeassistant/custom_components/nyra/events.py \
  homeassistant/custom_components/nyra/__init__.py \
  tests/homeassistant/test_events.py
git commit -m "feat: consume Router events in Home Assistant"
```

---

### Task 7: Implement the Home Assistant Conversation Agent Boundary

**Files:**
- Create: `homeassistant/custom_components/nyra/conversation.py`
- Create: `tests/homeassistant/test_conversation_core.py`
- Modify: `homeassistant/custom_components/nyra/__init__.py`

**Interfaces:**
- Registers a Home Assistant conversation agent for the config entry.
- Converts HA conversation input into `NyraRequest`.
- Uses `SessionManager` for session/request IDs.
- Uses `NyraRouterClient` for exactly one Router request.
- `ha_assist` includes authoritative HA user identity only when available.
- `ha_speaker` supplies source/device/area but does not infer personal identity.
- Router clarification preserves active request ID.
- Terminal response completes active request.
- Controlled unavailable/failure text is returned without local Assist/LLM fallback.

- [ ] **Step 1: Write failing adapter-core tests**

Keep request-building logic callable without a full HA runtime and test:

```text
authenticated HA user -> ha_assist + TrustedIdentity
speaker source -> ha_speaker + identity=None
language/source/area propagated
clarification preserves request
terminal result clears request
new intent receives new request
```

- [ ] **Step 2: Run core tests RED**

```bash
pytest -q tests/homeassistant/test_conversation_core.py
```

Expected: import/module failure.

- [ ] **Step 3: Implement request/result mapping**

Use actual current shared models (`NyraRequest`, `RequestSource`, `TrustedIdentity`, `NyraRequestResponse`).

Do not add duplicate protocol DTOs.

- [ ] **Step 4: Implement HA-facing `ConversationEntity` wrapper**

The HA-facing class should contain as little logic as possible: obtain HA fields, call the pure mapping/client/session layer, and convert text/status to HA `ConversationResult`.

Because this repository intentionally does not install the full `homeassistant` Python package as a test dependency, isolate HA imports so pure adapter tests remain runnable in the normal Nyra `.venv`. Final API compatibility is verified during deployment in the actual HA runtime.

- [ ] **Step 5: Run core tests GREEN**

```bash
pytest -q tests/homeassistant/test_conversation_core.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add homeassistant/custom_components/nyra/conversation.py \
  homeassistant/custom_components/nyra/__init__.py \
  tests/homeassistant/test_conversation_core.py
git commit -m "feat: add Nyra Home Assistant conversation agent"
```

---

### Task 8: Add Config Flow, Manifest, and Config-Entry Lifecycle

**Files:**
- Create: `homeassistant/custom_components/nyra/manifest.json`
- Create: `homeassistant/custom_components/nyra/config_flow.py`
- Modify: `homeassistant/custom_components/nyra/__init__.py`
- Test: `tests/homeassistant/test_config_core.py`

**Interfaces:**
- Config values: Router base URL and optional existing ingress token.
- Setup checks `/ready`.
- Successful setup constructs client/session/speaker/event runtime and registers conversation platform/agent.
- Unload stops event client and unregisters/releases runtime state.
- Reload performs a clean stop/start.

- [ ] **Step 1: Write failing pure config-validation tests**

Test URL normalization, default timeout, optional token handling, and readiness result mapping without requiring HA imports.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/homeassistant/test_config_core.py
```

- [ ] **Step 3: Add manifest/config flow/lifecycle**

`manifest.json` must identify the integration as `nyra`, use `config_flow: true`, and declare only runtime requirements actually needed beyond HA-provided libraries.

No YAML-only setup path is introduced.

- [ ] **Step 4: Verify integration Python syntax independently**

```bash
python -m compileall -q homeassistant/custom_components/nyra
```

Expected: no output/errors.

- [ ] **Step 5: Run config tests GREEN**

```bash
pytest -q tests/homeassistant/test_config_core.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add homeassistant/custom_components/nyra tests/homeassistant/test_config_core.py
git commit -m "feat: add Nyra Home Assistant integration setup"
```

---

### Task 9: Define the ESPHome Speaker Output Boundary and Wake/Close Feedback Hooks

**Files:**
- Modify: `homeassistant/custom_components/nyra/speaker.py`
- Create: `homeassistant/custom_components/nyra/esphome.py`
- Test: `tests/homeassistant/test_esphome_output.py`
- Documentation/reference: existing speaker configuration in the user's HA/ESPHome deployment is applied only during deployment, not guessed into repository code.

**Interfaces:**
- `EspHomeSpeakerOutput` implements `SpeakerOutputPort` through Home Assistant service/entity calls.
- Semantic effect names remain stable inside Nyra; device/entity IDs are resolved/configured at the HA boundary.
- Opening wake sound remains locally initiated by the speaker/wake-word path and must not depend on Router.
- Closing sound + blue blink is invoked from correlated `SESSION_CLOSED`.
- `speaking_purple` selects an audio-reactive purple speaker effect; firmware/device implementation performs audio-level modulation.

- [ ] **Step 1: Write failing output-adapter tests with fake HA service caller**

Verify each semantic output produces exactly the expected abstract HA service/effect request and target source.

Do not assert real user entity IDs in repository tests.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/homeassistant/test_esphome_output.py
```

- [ ] **Step 3: Implement output adapter**

Keep physical speaker identifiers/configuration external to Router and avoid hard-coding one home's entity IDs into shared protocol.

Expose a clear hook/helper for the speaker's local wake-word handler to trigger the mandatory opening sound and `LISTENING` feedback immediately.

- [ ] **Step 4: Run GREEN**

```bash
pytest -q tests/homeassistant/test_esphome_output.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add homeassistant/custom_components/nyra/speaker.py \
  homeassistant/custom_components/nyra/esphome.py \
  tests/homeassistant/test_esphome_output.py
git commit -m "feat: add ESPHome speaker output bridge"
```

---

### Task 10: Contract Invariants, Documentation, and Repository Verification

**Files:**
- Create: `tests/homeassistant/test_milestone2_invariants.py`
- Modify: `ARCHITECTURE.md`
- Modify: `docs/state/CURRENT_STATE.md`
- Modify: `ROADMAP.md` only if project convention marks completed milestone items there
- Modify: `README.md` only for user-facing setup/navigation if warranted by existing style

**Interfaces:**
- Tests protect Milestone 2 invariants against future regression.
- Docs explicitly state HA is migrated to the v1 Router path and no parallel/legacy HA route exists.
- Docs distinguish HA migration from later Voice/Identity/Memory/Skills/LLM migrations.

- [ ] **Step 1: Add invariant tests**

At minimum assert:

- no old interaction-detail state values are exposed as speaker states;
- no generic `WAITING` speaker state;
- `POST /v1/requests` is the configured request path;
- client has no retry loop/configuration;
- speaker rendering map matches approved colors/effects;
- clarification/listening share visual rendering;
- Job speaking does not require session-open state;
- source-targeted event dispatch is mandatory.

- [ ] **Step 2: Run all Home Assistant + affected Router tests**

```bash
pytest -q tests/homeassistant tests/protocol/test_events.py \
  tests/router/test_event_broker.py \
  tests/router/test_event_api.py \
  tests/router/test_request_lifecycle.py
```

Expected: PASS.

- [ ] **Step 3: Update architecture/current-state docs**

Document:

```text
HA Assist/Speaker -> custom_components/nyra -> POST /v1/requests -> Router
Router -> WS /v1/events -> HA speaker bridge -> ESPHome speaker
```

State explicitly that Home Assistant has no legacy/fallback Nyra route.

Do not mark biometric identity, Voice specialist migration, Memory, Skills, or LLM migration complete.

- [ ] **Step 4: Run the full repository suite**

```bash
pytest -q
```

Expected: all tests pass. Do not claim completion from focused tests alone.

- [ ] **Step 5: Run compile/syntax verification**

```bash
python -m compileall -q router shared tests homeassistant/custom_components/nyra
bash -n deploy/bootstrap/router.sh
```

Expected: no output/errors.

- [ ] **Step 6: Commit**

```bash
git add tests/homeassistant ARCHITECTURE.md docs/state/CURRENT_STATE.md ROADMAP.md README.md
git commit -m "docs: complete Home Assistant adapter milestone"
```

Only stage documentation files that actually changed.

---

### Task 11: Deploy to the Real Home Assistant Instance and Validate End-to-End

**Files outside repository installation target:**
- Deploy repository `homeassistant/custom_components/nyra/` to `/config/custom_components/nyra/` on Home Assistant.
- Apply any required HA/ESPHome speaker-side patch through `/config`, preserving the repository as source of truth for reusable integration code.

**Interfaces:**
- Real HA config entry points to the deployed `nyra-router` on port `8090`.
- Existing ingress token is configured if Router requires it.
- Real speaker source IDs are mapped at the HA boundary.
- Wake opening sound is local.
- Router events reach only the owning speaker.

- [ ] **Step 1: Package deployment overlay**

Create a deployment archive from the verified repository files rather than editing HA manually file-by-file.

- [ ] **Step 2: Install integration under HA `/config/custom_components/nyra/`**

Restart/reload Home Assistant as required by HA custom-integration loading rules.

- [ ] **Step 3: Configure Nyra through the HA UI**

Verify setup succeeds only when Router `/ready` is ready.

- [ ] **Step 4: Validate an HA Assist text request**

Confirm:

```text
HA -> /v1/requests -> Router -> HA ConversationResult
```

and inspect Router/Control Center correlation.

- [ ] **Step 5: Validate a real speaker session**

Acceptance sequence:

```text
wake word
-> opening sound
-> white fast pulse
-> identifying warm-white comet
-> 2-blink identity feedback
-> turquoise or rainbow processing
-> optional yellow tool comet
-> purple speaking
-> Router SESSION_CLOSED
-> closing sound + blue blink
-> idle
```

- [ ] **Step 6: Validate clarification**

Confirm:

```text
same session_id
same request_id
new trace_id
white fast pulse while waiting/listening
```

and timeout closes with closing feedback.

- [ ] **Step 7: Validate new intent**

Confirm same active session can produce a new request/new trace when appropriate.

- [ ] **Step 8: Validate concurrent speakers**

Run overlapping requests on two speakers and verify no visual/audio cross-routing.

- [ ] **Step 9: Validate Job behavior**

Confirm deferred Job/Behavior waiting produces no persistent waiting visual; confirm a Job that intentionally speaks uses purple `SPEAKING` without wake/open/listening lifecycle.

- [ ] **Step 10: Capture final verification evidence**

Record exact commands/tests plus real HA/Router observations in `docs/state/CURRENT_STATE.md` only after they have actually passed.

- [ ] **Step 11: Final commit and push**

```bash
git add docs/state/CURRENT_STATE.md
git commit -m "docs: record Home Assistant adapter validation"
git push
```

Do not create this commit if the deployment acceptance checks have not actually passed.

---

## Final Verification Gate

Before declaring Milestone 2 complete, all of the following must be true:

```bash
pytest -q
python -m compileall -q router shared tests homeassistant/custom_components/nyra
bash -n deploy/bootstrap/router.sh
```

And real Home Assistant acceptance must confirm:

```text
1. definitive HA -> Router path works
2. no legacy fallback exists
3. session/request/trace correlation is correct
4. speaker state arrives in real time through WS /v1/events
5. source routing isolates concurrent speakers
6. wake opening sound is local and immediate
7. local = turquoise comet
8. global = rainbow comet
9. tool = yellow comet
10. identity = warm-white comet + exactly two result blinks
11. listening/clarification = fast pulsing white
12. speaking = audio-reactive purple
13. session close = closing sound + blue blink -> idle
14. deferred Job waiting does not remain visible
15. Job speech uses SPEAKING without fake listening session
```

Milestone 3 (Identity and Voice) begins only after this gate is satisfied.
