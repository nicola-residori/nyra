# Push-to-record Voice Enrollment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a Home Assistant enrollment screen where one button records one Nyra speaker sample without a wake word, stops on trailing silence, submits it to Router/Speaker-ID, and renders green or red result feedback.

**Architecture:** Home Assistant remains the authenticated enrollment orchestrator and Router remains the durable session owner. A dedicated ESPHome capture mode sends `ENROLLMENT_CAPTURE` to Home Assistant; only that mode is converted to Router `ENROLLMENT` metadata, while ordinary Assist audio remains `IDENTIFICATION`. The speaker performs bounded speech/silence detection and displays recording/result feedback locally; a custom Home Assistant panel exposes phrase, progress, record, and terminate controls through authenticated WebSocket commands.

**Tech Stack:** Python 3.14, Home Assistant 2026.8 custom integration and WebSocket API, FastAPI, SQLite, ESPHome 2026.8.2, ESP-IDF C++, vanilla Web Components.

**Spec:** `docs/superpowers/specs/2026-09-07-push-to-record-enrollment-design.md`

## Global Constraints

- Only Nyra Mansarda may receive firmware during practical validation.
- Enrollment capture must never open Assist, run STT, invoke the conversation agent, or produce conversational TTS.
- The authenticated Home Assistant user is the canonical profile user; the browser and firmware never supply a profile user ID.
- One button press creates at most one audio attempt; duplicate presses while recording are rejected.
- A rejected/failed sample does not advance phrase or progress.
- All firmware terminal paths restore microphone and wake-word operation.
- No commit or push is performed without explicit user authorization.

---

### Task 1: Make Router enrollment start idempotent per speaker

**Files:**
- Modify: `router/enrollment.py`
- Modify: `router/api/enrollments.py`
- Test: `tests/router/test_enrollment_sessions.py`
- Test: `tests/integration/test_enrollment_flow.py`

**Interfaces:**
- Consumes: `EnrollmentService.start(profile_user_id, source_id, language, target_count)`.
- Produces: the same method returns the existing active session for the same user/source; it raises `EnrollmentConflict` when another user owns the active source; `GET /v1/enrollments/active/{source_id}` returns the active session or 404.

- [ ] **Step 1: Write failing tests for repeat start and source ownership**

```python
def test_start_is_idempotent_for_same_user_and_source(tmp_path):
    service = enrollment_service(tmp_path)
    first = service.start("user-nicola", "nyra-mansarda", "it-IT", 6)
    second = service.start("user-nicola", "nyra-mansarda", "it-IT", 6)
    assert second.session_id == first.session_id
    assert second.accepted_sample_ids == ()

def test_start_rejects_active_source_owned_by_another_user(tmp_path):
    service = enrollment_service(tmp_path)
    service.start("user-nicola", "nyra-mansarda", "it-IT", 6)
    with pytest.raises(EnrollmentConflict, match="active enrollment"):
        service.start("user-alice", "nyra-mansarda", "it-IT", 6)
```

Add an API assertion that the ownership conflict is HTTP 409 with a stable `ACTIVE_ENROLLMENT_CONFLICT` detail.
Add an API assertion that `GET /v1/enrollments/active/nyra-mansarda` returns the active session and returns 404 after termination.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
pytest -q tests/router/test_enrollment_sessions.py tests/integration/test_enrollment_flow.py
```

Expected: the repeated call currently creates a second session or the ownership conflict is not typed as required.

- [ ] **Step 3: Add an active-session lookup and typed conflict**

Add these interfaces in `router/enrollment.py`:

```python
class EnrollmentConflict(RuntimeError):
    pass

def get_active_for_source(self, source_id: str) -> EnrollmentSession | None:
    with self._lock, self._connect() as connection:
        row = connection.execute(
            "SELECT * FROM enrollment_sessions WHERE source_id = ? AND status = 'ACTIVE'",
            (source_id,),
        ).fetchone()
    return None if row is None else self._from_row(row)
```

Implement `get_active_for_source` as one SQLite query filtered by `source_id` and `status = 'ACTIVE'`. In `start`, return that session when `profile_user_id` matches; otherwise raise `EnrollmentConflict`. Map the exception to HTTP 409 in `router/api/enrollments.py`, and expose the active-source GET endpoint through the same bearer-authenticated router.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all tests pass.

- [ ] **Step 5: Check the diff without committing**

```bash
git diff --check -- router/enrollment.py router/api/enrollments.py tests/router/test_enrollment_sessions.py tests/integration/test_enrollment_flow.py
```

---

### Task 2: Separate direct enrollment capture from normal Assist audio

**Files:**
- Modify: `homeassistant/custom_components/nyra/audio.py`
- Modify: `homeassistant/custom_components/nyra/enrollment.py`
- Test: `tests/homeassistant/test_audio_ingress.py`
- Test: `tests/homeassistant/test_enrollment.py`

**Interfaces:**
- Consumes: speaker START frames with `purpose` equal to `IDENTIFICATION` or `ENROLLMENT_CAPTURE`.
- Produces: `SpeakerAudioStart.capture_kind`, `EnrollmentCoordinator.audio_metadata`, and explicit rejection when a direct capture has no matching active session.

- [ ] **Step 1: Write failing protocol and isolation tests**

```python
def test_normal_identification_is_never_rewritten_during_enrollment():
    coordinator = active_coordinator()
    metadata = identification_start(source_id="nyra-mansarda")
    assert coordinator.audio_metadata(metadata).purpose == "IDENTIFICATION"

def test_explicit_enrollment_capture_is_bound_to_active_session():
    coordinator = active_coordinator()
    metadata = enrollment_capture_start(source_id="nyra-mansarda")
    bound = coordinator.audio_metadata(metadata)
    assert bound.purpose == "ENROLLMENT"
    assert bound.user_id == "authenticated-user"
    assert bound.enrollment_session_id == "enr_1"

def test_explicit_enrollment_capture_without_session_is_rejected():
    with pytest.raises(EnrollmentConflict, match="no active enrollment"):
        EnrollmentCoordinator(FakeClient()).audio_metadata(
            enrollment_capture_start(source_id="nyra-mansarda")
        )
```

- [ ] **Step 2: Run the tests and verify RED**

```bash
pytest -q tests/homeassistant/test_audio_ingress.py tests/homeassistant/test_enrollment.py
```

Expected: active enrollment currently rewrites ordinary identification audio and the public ingress rejects `ENROLLMENT_CAPTURE`.

- [ ] **Step 3: Add the explicit capture-kind contract**

Keep Router DTOs unchanged. Extend the speaker-facing START parser so:

```python
SPEAKER_CAPTURE_PURPOSES = {"IDENTIFICATION", "ENROLLMENT_CAPTURE"}

@dataclass(frozen=True)
class SpeakerAudioStart:
    audio_stream_id: str
    source_id: str
    language: str
    capture_kind: str
    audio_format: str = "pcm_s16le"
    sample_rate: int = 16000
    channels: int = 1
```

Correlation adds Router session/request IDs after parsing. `EnrollmentCoordinator.audio_metadata` returns an ordinary `IdentificationAudioStart` for `IDENTIFICATION`; it creates `EnrollmentAudioStart` only for `ENROLLMENT_CAPTURE`. Remove the old rule that rewrites every capture from an active source.

- [ ] **Step 4: Return a stable WebSocket error for missing/mismatched sessions**

Map the coordinator conflict to `NO_ACTIVE_ENROLLMENT` or `ENROLLMENT_SOURCE_MISMATCH` in the public ingress error frame. Do not open a Router stream when correlation fails.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: all tests pass.

---

### Task 3: Add deterministic on-device speech-end detection

**Files:**
- Create: `esphome/components/nyra_audio_ingress/voice_activity_detector.h`
- Modify: `esphome/components/nyra_audio_ingress/nyra_audio_ingress.h`
- Modify: `esphome/components/nyra_audio_ingress/nyra_audio_ingress.cpp`
- Modify: `esphome/components/nyra_audio_ingress/__init__.py`
- Create: `tests/esphome/test_voice_activity_detector.py`
- Modify: `tests/esphome/test_nyra_audio_tee.py`

**Interfaces:**
- Produces: `VoiceActivityDetector::update(const int16_t *samples, size_t count, uint32_t now_ms)` and `NyraAudioIngress::start_enrollment_capture()`.
- Capture defaults: speech RMS 700, continuation RMS 450, speech-on window 120 ms, trailing silence 900 ms, no-speech timeout 8 s, maximum duration 15 s.

- [ ] **Step 1: Write a host-compiled failing detector test**

Create a pytest test that writes a small C++ program to `tmp_path`, includes `voice_activity_detector.h`, feeds silence, voiced samples, and trailing silence, then compiles and runs it with `c++ -std=c++17`. The assertions must cover:

```cpp
assert(vad.update(silence, 160, 1000) == CaptureDecision::WAITING_FOR_SPEECH);
assert(vad.update(speech, 160, 1200) == CaptureDecision::SPEAKING);
assert(vad.update(silence, 160, 2200) == CaptureDecision::COMPLETE);
```

Add separate cases for `NO_SPEECH_TIMEOUT` at 8 seconds and `MAX_DURATION` at 15 seconds.

- [ ] **Step 2: Run the new test and verify RED**

```bash
pytest -q tests/esphome/test_voice_activity_detector.py
```

Expected: compilation fails because the header and types do not exist.

- [ ] **Step 3: Implement the detector as an ESP-independent header**

Define:

```cpp
enum class CaptureDecision : uint8_t {
  WAITING_FOR_SPEECH,
  SPEAKING,
  COMPLETE,
  NO_SPEECH_TIMEOUT,
  MAX_DURATION,
};

struct VoiceActivityConfig {
  uint32_t speech_rms{700};
  uint32_t continuation_rms{450};
  uint32_t speech_on_ms{120};
  uint32_t trailing_silence_ms{900};
  uint32_t no_speech_timeout_ms{8000};
  uint32_t max_duration_ms{15000};
};
```

Use 64-bit accumulation for squared PCM samples, derive RMS, require consecutive voiced time before declaring speech, and use the lower continuation threshold once speech has begun. Keep the header free of ESPHome/FreeRTOS dependencies so the host test exercises the production algorithm.

- [ ] **Step 4: Run the detector test and verify GREEN**

Run the Step 2 command. Expected: pass.

- [ ] **Step 5: Write failing component wiring tests**

Extend `tests/esphome/test_nyra_audio_tee.py` to assert:

```python
assert "start_identification_stream" in source
assert "start_enrollment_capture" in source
assert 'root["purpose"] = this->capture_purpose_' in source
assert '"ENROLLMENT_CAPTURE"' in source
assert "VoiceActivityDetector" in header
assert "CaptureDecision::COMPLETE" in source
assert "CaptureDecision::NO_SPEECH_TIMEOUT" in source
```

- [ ] **Step 6: Run the component test and verify RED**

```bash
pytest -q tests/esphome/test_nyra_audio_tee.py
```

- [ ] **Step 7: Integrate capture modes and terminal results**

Rename the ordinary entry point to `start_identification_stream()` and keep `end_stream()` for Assist VAD. Add `start_enrollment_capture()` which resets the VAD and selects `ENROLLMENT_CAPTURE`. In `on_microphone_data_`, feed PCM to the detector before queueing; request END on `COMPLETE` or `MAX_DURATION`; produce a local rejected terminal state on `NO_SPEECH_TIMEOUT`.

Update RESULT parsing to support Router identification `outcome` and enrollment `status`:

```cpp
const std::string status = root["result"]["status"] | "";
if (status == "ACCEPTED") this->finish_(true, false);
else if (status == "REJECTED") this->finish_(false, true);
else if (status == "FAILED") this->finish_(false, false);
```

Expose the VAD timings and thresholds through the ESPHome schema with the defaults listed above.

- [ ] **Step 8: Run ESPHome tests and verify GREEN**

```bash
pytest -q tests/esphome/test_voice_activity_detector.py tests/esphome/test_nyra_audio_tee.py
```

---

### Task 4: Expose one direct capture button on each Nyra speaker

**Files:**
- Modify: `esphome/packages/nyra-speaker.yaml`
- Modify: `homeassistant/custom_components/nyra/esphome.py`
- Test: `tests/esphome/test_nyra_audio_tee.py`
- Test: `tests/homeassistant/test_speaker.py`

**Interfaces:**
- Produces: ESPHome entity named `Nyra Enrollment Capture` and `EspHomeSpeakerOutput.record_enrollment_sample(source_id)`.

- [ ] **Step 1: Write failing discovery and action tests**

```python
async def test_record_enrollment_presses_discovered_capture_button():
    output = EspHomeSpeakerOutput({
        "nyra-mansarda": SpeakerTarget(
            light_entity="light.nyra_status_ring",
            enrollment_capture_button="button.nyra_enrollment_capture",
        )
    }, call_service)
    await output.record_enrollment_sample("nyra-mansarda")
    assert calls == [("button", "press", {
        "entity_id": "button.nyra_enrollment_capture"
    })]
```

Add a package test requiring `micro_wake_word.stop`, direct microphone capture, `start_enrollment_capture`, and restoration in accepted/rejected/failed terminal callbacks.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
pytest -q tests/homeassistant/test_speaker.py tests/esphome/test_nyra_audio_tee.py
```

- [ ] **Step 3: Add the ESPHome template button and lifecycle**

The button sequence must:

```yaml
- platform: template
  id: nyra_enrollment_capture
  name: "Nyra Enrollment Capture"
  entity_category: diagnostic
  on_press:
    - micro_wake_word.stop:
    - microphone.capture: i2s_mics
    - light.turn_on:
        id: status_ring
        effect: "nyra_listening_white_fast"
    - lambda: 'id(nyra_audio_tee).start_enrollment_capture();'
```

Configure `on_accepted`, `on_rejected`, and `on_failed` on `nyra_audio_ingress`. Each path stops microphone capture and restarts `micro_wake_word`; accepted runs the existing green two-blink sequence, while rejected/failed run the red two-blink sequence. Ordinary `voice_assistant.on_listening` must call `start_identification_stream()`.

- [ ] **Step 4: Discover and invoke the capture entity from Home Assistant**

Add `ENROLLMENT_CAPTURE_NAME = "Nyra Enrollment Capture"`, store it in `SpeakerTarget.enrollment_capture_button`, and implement:

```python
async def record_enrollment_sample(self, source_id: str) -> None:
    target = await self._target(source_id)
    if target is None or target.enrollment_capture_button is None:
        raise SpeakerUnavailable("enrollment capture button is unavailable")
    await self._call_service("button", "press", {
        "entity_id": target.enrollment_capture_button,
    })
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: pass.

---

### Task 5: Add authenticated recording orchestration and reload recovery

**Files:**
- Modify: `homeassistant/custom_components/nyra/enrollment.py`
- Modify: `homeassistant/custom_components/nyra/client.py`
- Modify: `homeassistant/custom_components/nyra/__init__.py`
- Modify: `homeassistant/custom_components/nyra/services.yaml`
- Modify: `homeassistant/custom_components/nyra/translations/en.json`
- Modify: `homeassistant/custom_components/nyra/translations/it.json`
- Test: `tests/homeassistant/test_enrollment.py`

**Interfaces:**
- Produces: `EnrollmentCoordinator.async_record(authenticated_user_id, session_id)`, `EnrollmentCoordinator.async_restore(source_ids)`, capture state, and `nyra.record_enrollment_sample`.
- Consumes: `EspHomeSpeakerOutput.record_enrollment_sample(source_id)`.

- [ ] **Step 1: Write failing coordinator tests**

Cover these exact behaviors:

```python
session = await coordinator.async_start("user-nicola", "nyra-mansarda", "it-IT", 6)
recording = await coordinator.async_record("user-nicola", session["session_id"])
assert recording["capture_state"] == "RECORDING"
assert output.recorded == ["nyra-mansarda"]

with pytest.raises(EnrollmentConflict, match="already recording"):
    await coordinator.async_record("user-nicola", session["session_id"])

with pytest.raises(EnrollmentUnauthorized):
    await coordinator.async_record("user-alice", session["session_id"])
```

Also test that an idempotent start rebinds the Router-returned session after Home Assistant reload and that an accepted/rejected result clears `RECORDING` before notifying UI state.
Test `async_restore(["nyra-mansarda"])` by returning the active-source session from the fake Router client and asserting that `state_for_user("user-nicola")` exposes it without creating a new session.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
pytest -q tests/homeassistant/test_enrollment.py
```

- [ ] **Step 3: Implement record state and service**

Add `NyraRouterClient.async_get_active_enrollment(source_id)`. Inject `record_output` into `EnrollmentCoordinator`. Track capture state per source and expose `state_for_user(user_id)`. `async_restore(source_ids)` queries Router for each discovered Nyra source and binds every ACTIVE response. `async_record` validates ownership and ACTIVE status, sets `RECORDING`, notifies, invokes the speaker, and rolls back to `READY` if invocation fails. `async_record_result` sets `PROCESSING`, records the Router attempt, then publishes `ACCEPTED`, `REJECTED`, `FAILED`, or `COMPLETED` state. Call `async_restore(targets.keys())` during integration setup before registering the panel.

Register:

```yaml
record_enrollment_sample:
  name: Record enrollment sample
  fields:
    session_id:
      required: true
      selector:
        text:
```

The handler always derives the user ID from `call.context.user_id`.

- [ ] **Step 4: Remove duplicate HA blink commands for sample results**

Firmware owns accepted/rejected/failed blink feedback because it receives the terminal RESULT frame. Keep Home Assistant completion announcement and session-state notification, but do not press the identity feedback button a second time.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run the Step 2 command. Expected: pass.

---

### Task 6: Build the Home Assistant enrollment panel

**Files:**
- Create: `homeassistant/custom_components/nyra/panel.py`
- Create: `homeassistant/custom_components/nyra/frontend/nyra-enrollment-panel.js`
- Modify: `homeassistant/custom_components/nyra/__init__.py`
- Modify: `homeassistant/custom_components/nyra/manifest.json`
- Modify: `homeassistant/custom_components/nyra/translations/en.json`
- Modify: `homeassistant/custom_components/nyra/translations/it.json`
- Create: `tests/homeassistant/test_enrollment_panel.py`

**Interfaces:**
- Produces WebSocket commands: `nyra/enrollment/state`, `nyra/enrollment/start`, `nyra/enrollment/record`, `nyra/enrollment/terminate`.
- Produces sidebar panel URL `/nyra-enrollment` titled `Registrazione voce`.

- [ ] **Step 1: Write failing backend panel tests**

Use fake authenticated WebSocket connections and assert:

```python
await ws_start(hass, connection_for("user-nicola"), {
    "id": 1,
    "type": "nyra/enrollment/start",
    "source_id": "nyra-mansarda",
    "language": "it-IT",
    "sample_count": 6,
})
assert coordinator.started[0]["authenticated_user_id"] == "user-nicola"

await ws_record(hass, connection_for("user-nicola"), {
    "id": 2,
    "type": "nyra/enrollment/record",
    "session_id": "enr_1",
})
assert coordinator.recorded == [("user-nicola", "enr_1")]
```

Test that unauthenticated connections are rejected and backend exceptions return localized, stable error codes rather than `unknown_error`.

- [ ] **Step 2: Run the backend panel test and verify RED**

```bash
pytest -q tests/homeassistant/test_enrollment_panel.py
```

- [ ] **Step 3: Register the panel and WebSocket commands**

Use Home Assistant `websocket_api.websocket_command` handlers and `connection.user.id` for ownership. Serve the bundled, data-free JavaScript as a static integration asset and register a custom sidebar panel with `frontend.async_register_built_in_panel`; all state and mutations still require the authenticated WebSocket connection. Unregister the panel on integration unload.

Responses contain only:

```json
{
  "session_id": "enr_0123456789abcdef0123456789abcdef",
  "source_id": "nyra-mansarda",
  "language": "it-IT",
  "status": "ACTIVE",
  "capture_state": "READY",
  "accepted_count": 0,
  "target_count": 6,
  "current_phrase": "La luce è accesa.",
  "last_reason_code": null
}
```

- [ ] **Step 4: Write the frontend panel and static tests**

The vanilla custom element renders speaker, language, sample count, current phrase, `X/N`, latest localized result, **Avvia registrazione**, **Registra campione**, and **Termina**. Disable record unless state is `READY`; display `RECORDING` as `In ascolto…` and `PROCESSING` as `Invio del campione…`.

Add source-level assertions in `tests/homeassistant/test_enrollment_panel.py` for all four WebSocket message types, button labels, current phrase, progress, error rendering, and the absence of `conversation.process`, `assist_pipeline`, or user-ID inputs.

- [ ] **Step 5: Run panel tests and verify GREEN**

Run the Step 2 command. Expected: pass.

---

### Task 7: Regression, deployment, and physical Mansarda verification

**Files:**
- Modify: `docs/state/CURRENT_STATE.md`
- Modify: `docs/deployment/ESPHOME_SPEAKERS.md`
- Modify: `docs/superpowers/plans/2026-09-01-milestone-3-identity-and-voice.md`

**Interfaces:**
- Consumes all preceding tasks.
- Produces deployed Home Assistant integration, Router service, and Nyra Mansarda firmware plus recorded Nicola profile.

- [ ] **Step 1: Run focused and full automated verification**

```bash
pytest -q tests/router/test_enrollment_sessions.py \
  tests/integration/test_enrollment_flow.py \
  tests/homeassistant/test_audio_ingress.py \
  tests/homeassistant/test_enrollment.py \
  tests/homeassistant/test_enrollment_panel.py \
  tests/homeassistant/test_speaker.py \
  tests/esphome/test_voice_activity_detector.py \
  tests/esphome/test_nyra_audio_tee.py
pytest -q
git diff --check
```

Expected: all tests pass; no whitespace errors.

- [ ] **Step 2: Compile the exact Mansarda configuration before deployment**

Back up `/config/esphome/packages/nyra-speaker.yaml` and the installed Nyra integration. Copy the reviewed files, run `ha core check`, restart Home Assistant, and confirm `/ready` for Router and Speaker-ID. Compile `nyra-mansarda.yaml` and verify the build contains `Nyra Enrollment Capture` and `ENROLLMENT_CAPTURE` before OTA.

- [ ] **Step 3: Install firmware only on Nyra Mansarda**

Use ESPHome OTA for `nyra-mansarda.yaml`. Do not compile or install `nyra-soggiorno.yaml`. Verify `192.168.0.141:6053`, the ESPHome API connection, and the absence of boot loops or audio-ingress errors.

- [ ] **Step 4: Run the physical six-sample enrollment**

Open `/nyra-enrollment`, select Mansarda, six samples, and Italian. For each phrase, press **Registra campione**, speak without saying `Nyra`, stop speaking, and verify white recording followed by green acceptance or red rejection. Query Router session state and Speaker-ID `speaker_profiles` after each accepted attempt. Completion requires six accepted sample IDs and a usable profile row for Nicola's authenticated Home Assistant user ID.

- [ ] **Step 5: Verify normal behavior after enrollment**

Say `Nyra`, wait for the normal cue, and ask `che ore sono`. Confirm normal listening/speaking lights and sound, the correct spoken time, one `IDENTIFIED` diagnostic for Nicola above the configured threshold, and no enrollment attempt added by the normal Assist request.

- [ ] **Step 6: Update project state without committing**

Mark Task 14 and the physical enrollment smoke-test step complete only after Step 5 succeeds. Record the deployed firmware build hash, HA validation result, Router/Speaker-ID health, and profile sample count in `docs/state/CURRENT_STATE.md`.
