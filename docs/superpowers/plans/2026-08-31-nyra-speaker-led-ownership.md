# Nyra Speaker LED Ownership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate competing writers on the Nyra speaker status ring so identity feedback is visibly protected, semantic Router states are deterministic, and purple speaking feedback follows actual local TTS playback.

**Architecture:** Router/HA remains the owner of semantic interaction visuals, keyed by stable `source_id`. ESPHome owns immediate wake/open feedback and actual playback feedback, while upstream Waveshare phase-driven LED writes are gated so they cannot overwrite a Nyra-owned interaction. Identity feedback remains a protected HA-side transient; playback temporarily overrides semantic visuals and releases ownership when audio ends.

**Tech Stack:** Python 3, Home Assistant custom integration, Pydantic shared protocol DTOs, ESPHome 2026.8.2 YAML/C++ lambdas, pytest.

**Spec:** `docs/superpowers/specs/2026-08-31-nyra-speaker-led-ownership-design.md`

## Global Constraints

- During an active Nyra interaction the status ring has one semantic owner: Nyra.
- Upstream Waveshare voice/audio/wake-word behavior must not be forked or duplicated beyond the smallest maintainable LED-write gate.
- Wake-word opening feedback remains local.
- `SPEAKING` follows actual local TTS/media playback, not a Router timing guess.
- Identity feedback remains exactly two visible blinks and protects the configured feedback window.
- Subsequent processing states are queued and restored after identity feedback.
- No artificial delays are added to warm-white, turquoise, rainbow, or other semantic stages.
- `nyra_listening_white_fast` is a continuous fast white fade, not a pulse.
- Stable read-only `Nyra Source ID` remains the source/device join key.
- Missing target resolution must never fall back to another speaker.
- True audio-reactive wording/behavior is allowed only if real playback amplitude is available; otherwise retain an animated purple speaking effect.
- Temporary `NYRA_DIAG_*` instrumentation must not remain in production.
- Public repository files must not contain real installation-specific speaker inventory or credentials.

---

## File Structure

- `esphome/packages/nyra-speaker.yaml` — reusable Nyra firmware package; owns Nyra ring arbitration, effects, wake/open behavior, and local playback override.
- `homeassistant/custom_components/nyra/speaker.py` — semantic speaker state machine; identity transient and semantic-state restoration.
- `homeassistant/custom_components/nyra/esphome.py` — source-id-to-HA-device discovery and semantic effect service calls.
- `tests/esphome/test_nyra_local_voice_visuals.py` — static contract tests for local wake/listening/playback LED ownership.
- `tests/esphome/test_nyra_speaker_package.py` — reusable package/provisioning contract checks if existing test names/coverage require ownership assertions.
- `tests/homeassistant/test_speaker.py` — state-machine identity protection and restoration.
- `tests/homeassistant/test_esphome.py` — target isolation and effect dispatch.
- `docs/superpowers/specs/2026-08-31-nyra-speaker-led-ownership-design.md` — approved design.
- `docs/superpowers/plans/2026-08-31-nyra-speaker-led-ownership.md` — this implementation plan.

### Task 1: Protect identity feedback in the HA semantic state machine

**Files:**
- Modify: `homeassistant/custom_components/nyra/speaker.py`
- Test: `tests/homeassistant/test_speaker.py`

**Interfaces:**
- Consumes: `InteractionStateChanged`, `IdentityFeedbackEvent`, `SpeakerOutputPort`.
- Produces: existing `SpeakerStateMachine.handle_state()`, `handle_identity()`, `restore_processing()` behavior with a protected identity window and no diagnostic side effects.

- [ ] **Step 1: Add/confirm the failing regression test for a processing event arriving immediately after identity**

Add a test using a fake `SpeakerOutputPort` and controllable sleep that performs:

```python
await machine.handle_state(processing_local)
await machine.handle_state(identifying)
await machine.handle_identity(not_recognized)
await machine.handle_state(processing_local_after_identity)
await machine.handle_state(processing_global_after_identity)

assert output.calls[-1] == (
    "blink_identity",
    "nyra-mansarda",
    IdentityFeedback.NOT_RECOGNIZED,
    2,
)
```

Before releasing the controlled identity sleep, assert neither the pending local nor global state was rendered after the blink. Release the sleep and assert the latest pending state is rendered:

```python
assert output.calls[-1] == ("comet_rainbow", "nyra-mansarda")
```

- [ ] **Step 2: Run the focused regression test**

Run:

```bash
pytest -q tests/homeassistant/test_speaker.py -k 'identity'
```

Expected: the new regression test fails if a later semantic state can overwrite the identity transient; otherwise it documents the already-correct HA behavior and Task 1 becomes a cleanup-only GREEN change.

- [ ] **Step 3: Remove temporary speaker diagnostics and make only the minimal state-machine correction if RED exposed one**

Production `speaker.py` must contain no `print("NYRA_DIAG...")`, `_LOGGER.warning("NYRA_DIAG...")`, or diagnostic-only logging imports. Preserve the existing `IDENTITY_FEEDBACK_SECONDS = 0.65` unless the test demonstrates a state-machine defect; do not lengthen it to hide firmware races.

- [ ] **Step 4: Run focused state-machine tests**

Run:

```bash
pytest -q tests/homeassistant/test_speaker.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add homeassistant/custom_components/nyra/speaker.py tests/homeassistant/test_speaker.py
git commit -m "test: protect identity feedback state"
```

### Task 2: Keep HA effect dispatch source-isolated and remove diagnostics

**Files:**
- Modify: `homeassistant/custom_components/nyra/esphome.py`
- Test: `tests/homeassistant/test_esphome.py`

**Interfaces:**
- Consumes: `source_id: str`, `IdentityFeedback`, discovered `SpeakerTarget`.
- Produces: `_effect(source_id, effect)` dispatch to exactly the resolved target, or no service call when unresolved.

- [ ] **Step 1: Write the missing-target and correct-target regression tests**

Cover both cases explicitly:

```python
await output.blink_identity(
    "nyra-mansarda",
    IdentityFeedback.NOT_RECOGNIZED,
    2,
)
assert calls == [
    (
        "light",
        "turn_on",
        {
            "entity_id": "light.nyra_mansarda_nyra_status_ring",
            "effect": "nyra_identity_red_2blink",
        },
    )
]
```

and:

```python
await output.blink_identity(
    "nyra-unknown",
    IdentityFeedback.NOT_RECOGNIZED,
    2,
)
assert calls == []
```

If a second fake speaker exists in the fixture, assert its entity ID never appears in the first speaker's call list.

- [ ] **Step 2: Run focused dispatch tests**

Run:

```bash
pytest -q tests/homeassistant/test_esphome.py -k 'identity or target or source'
```

Expected: PASS for existing correct behavior; any failure must be fixed without fallback matching or entity-name parsing.

- [ ] **Step 3: Remove all temporary `NYRA_DIAG_*` instrumentation from `esphome.py`**

Remove diagnostic logging added around `_effect()`, `_target()`, and `set_idle()`. Do not alter the working mapping:

```python
IdentityFeedback.RECOGNIZED: "nyra_identity_green_2blink"
IdentityFeedback.NOT_RECOGNIZED: "nyra_identity_red_2blink"
IdentityFeedback.IDENTITY_CHANGED: "nyra_identity_blue_2blink"
```

- [ ] **Step 4: Run the complete ESPHome-output Python tests**

Run:

```bash
pytest -q tests/homeassistant/test_esphome.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add homeassistant/custom_components/nyra/esphome.py tests/homeassistant/test_esphome.py
git commit -m "test: enforce speaker source isolation"
```

### Task 3: Introduce explicit Nyra ring ownership in the reusable ESPHome package

**Files:**
- Modify: `esphome/packages/nyra-speaker.yaml`
- Test: `tests/esphome/test_nyra_local_voice_visuals.py`

**Interfaces:**
- Consumes: upstream Waveshare voice-assistant phase callbacks and Nyra local wake/TTS callbacks.
- Produces: a local ownership flag/state that prevents upstream phase visuals from overwriting the ring while a Nyra interaction owns it.

- [ ] **Step 1: Write a failing static contract test for ownership arbitration**

The test must load/read `esphome/packages/nyra-speaker.yaml` and assert the package defines an internal Nyra ownership state, for example:

```yaml
globals:
  - id: nyra_ring_owned
    type: bool
    restore_value: no
    initial_value: 'false'
```

The exact integration technique must match what the pinned Waveshare package permits, but the test must also prove that Nyra wake/pipeline activation sets ownership before semantic visuals can arrive and that release occurs at terminal idle/session-close behavior.

- [ ] **Step 2: Run the ownership contract test and observe RED**

Run:

```bash
pytest -q tests/esphome/test_nyra_local_voice_visuals.py -k 'ownership'
```

Expected: FAIL because the current package has no explicit single-owner gate.

- [ ] **Step 3: Implement the smallest maintainable ownership gate**

Use one internal boolean/global (or the equivalent supported primitive) in `esphome/packages/nyra-speaker.yaml`.

Required state transitions:

```text
wake/open or Nyra pipeline start -> nyra_ring_owned = true
active semantic interaction      -> upstream phase LED writes cannot replace Nyra effects
terminal idle/session close      -> nyra_ring_owned = false
```

Do not duplicate the upstream voice-assistant state machine. If the pinned package exposes a script such as `control_leds`, wrap/override only the LED-writing entry point needed to honor `nyra_ring_owned`; leave microphone, wake-word, media-player, timers, and voice phases untouched.

- [ ] **Step 4: Run ownership tests**

Run:

```bash
pytest -q tests/esphome/test_nyra_local_voice_visuals.py -k 'ownership'
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add esphome/packages/nyra-speaker.yaml tests/esphome/test_nyra_local_voice_visuals.py
git commit -m "fix: give Nyra ownership of speaker ring"
```

### Task 4: Make listening a continuous fast white fade under Nyra ownership

**Files:**
- Modify: `esphome/packages/nyra-speaker.yaml`
- Test: `tests/esphome/test_nyra_local_voice_visuals.py`

**Interfaces:**
- Consumes: existing effect name `nyra_listening_white_fast`.
- Produces: the same stable effect name with continuous fast white-fade behavior.

- [ ] **Step 1: Write/retain a failing effect-shape test**

Assert `nyra_listening_white_fast` is not implemented as an upstream pulse alias and uses a continuous short-interval addressable lambda/automation that ramps white brightness up and down without changing hue.

The test should reject known upstream phase effects such as `Pulse Fast`, `Comet`, and `Wipe` as the implementation of the Nyra listening effect.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/esphome/test_nyra_local_voice_visuals.py -k 'listening'
```

Expected: FAIL if the package still behaves as a pulse or if the prior overlay was not incorporated into the repo.

- [ ] **Step 3: Implement the minimal continuous white fade**

Keep the public effect name:

```text
nyra_listening_white_fast
```

Use the already-approved fast continuous triangle-style white fade. Do not add a second listening effect or rename the HA contract.

- [ ] **Step 4: Run listening tests**

```bash
pytest -q tests/esphome/test_nyra_local_voice_visuals.py -k 'listening'
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add esphome/packages/nyra-speaker.yaml tests/esphome/test_nyra_local_voice_visuals.py
git commit -m "fix: use continuous white listening fade"
```

### Task 5: Give actual local TTS playback temporary visual priority

**Files:**
- Modify: `esphome/packages/nyra-speaker.yaml`
- Test: `tests/esphome/test_nyra_local_voice_visuals.py`

**Interfaces:**
- Consumes: local `voice_assistant`/media playback lifecycle exposed by the pinned Waveshare/ESPHome stack.
- Produces: `nyra_speaking_purple_audio` for the actual playback interval, then release back to Nyra semantic ownership/idle without upstream `Wipe` winning.

- [ ] **Step 1: Write a failing playback lifecycle test**

The static contract test must assert that the local playback start hook selects:

```text
nyra_speaking_purple_audio
```

and that playback completion releases the local speaking override rather than permanently turning semantic ownership off.

It must also reject `Wipe` as the Nyra speaking visual.

- [ ] **Step 2: Run RED**

```bash
pytest -q tests/esphome/test_nyra_local_voice_visuals.py -k 'tts or speaking or playback'
```

Expected: FAIL until playback priority and release are represented correctly.

- [ ] **Step 3: Implement playback override**

Use the actual local lifecycle available in the pinned stack. Start purple when TTS/media playback really starts. End the speaking override when playback finishes.

Do not claim amplitude reactivity unless the implementation has a real playback-level signal. If no such signal exists, retain the existing animated purple effect and name while documenting it as a speaking animation rather than PCM-reactive visualization.

The ownership sequence must be:

```text
Nyra semantic state
    -> actual playback starts
purple speaking override
    -> actual playback ends
latest Nyra semantic state or terminal idle
```

Do not synthesize a new Router `SPEAKING` event solely to drive this local behavior.

- [ ] **Step 4: Run playback tests**

```bash
pytest -q tests/esphome/test_nyra_local_voice_visuals.py -k 'tts or speaking or playback'
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add esphome/packages/nyra-speaker.yaml tests/esphome/test_nyra_local_voice_visuals.py
git commit -m "fix: bind speaker purple to TTS playback"
```

### Task 6: Prove no diagnostic code or ownership regression remains

**Files:**
- Test: `tests/homeassistant/test_speaker.py`
- Test: `tests/homeassistant/test_esphome.py`
- Test: `tests/esphome/test_nyra_local_voice_visuals.py`
- Potentially modify only files already touched above if verification exposes a defect.

**Interfaces:**
- Consumes: completed Tasks 1-5.
- Produces: clean production files and regression coverage.

- [ ] **Step 1: Scan for temporary diagnostics**

Run:

```bash
grep -Rni 'NYRA_DIAG' \
  homeassistant/custom_components/nyra \
  esphome/packages \
  tests || true
```

Expected: no production diagnostics. Test fixtures may contain the literal only if specifically testing its absence; otherwise no matches.

- [ ] **Step 2: Run focused M2/ESPHome tests**

```bash
pytest -q \
  tests/homeassistant/test_speaker.py \
  tests/homeassistant/test_esphome.py \
  tests/esphome/test_nyra_local_voice_visuals.py
```

Expected: PASS.

- [ ] **Step 3: Run full Python verification**

```bash
pytest -q
python -m compileall -q router shared homeassistant tests
```

Expected: all tests PASS and compileall exits 0.

- [ ] **Step 4: Validate ESPHome using the real private wrapper without committing it**

From the ESPHome configuration environment, validate the existing private speaker wrapper for `nyra-mansarda` using ESPHome 2026.8.2.

Expected: configuration valid; no duplicate IDs/hooks and no missing substitutions.

- [ ] **Step 5: Commit any verification-only corrections**

If no corrections were needed, skip this commit. Otherwise:

```bash
git add <only-files-corrected-during-verification>
git commit -m "fix: complete speaker LED ownership verification"
```

### Task 7: Deploy and perform live ownership verification

**Files:**
- Deployment target: `/config/custom_components/nyra/` on Home Assistant.
- Deployment target: private ESPHome `nyra-mansarda` configuration.
- No installation-specific runtime files are committed.

**Interfaces:**
- Consumes: verified repository state from Task 6.
- Produces: deployed HA adapter and flashed speaker firmware exhibiting deterministic visual ownership.

- [ ] **Step 1: Deploy the changed HA integration files**

Copy the verified `speaker.py` and `esphome.py` from the repository to:

```text
/config/custom_components/nyra/
```

Preserve the existing canonical `shared` deployment arrangement currently required by the M2 installation; this task does not redesign packaging.

Restart Home Assistant and verify there are no import/setup errors for `custom_components.nyra`.

- [ ] **Step 2: Update/flash `nyra-mansarda`**

Build and install the private wrapper that includes the updated public `esphome/packages/nyra-speaker.yaml`.

Verify the device reconnects at its reserved address and exposes the existing stable `Nyra Source ID`, status ring, and close-feedback entities.

- [ ] **Step 3: Run one live `Alexa -> Ciao` interaction with HA and ESPHome logs open**

Expected physical sequence:

```text
wake/open
-> fast continuous white listening fade
-> warm-white identifying
-> visible red two-blink for NOT_RECOGNIZED
-> current semantic processing visual restored
-> purple for actual TTS playback
-> terminal idle/close behavior
```

- [ ] **Step 4: Verify the log ordering**

HA must show the identity semantic effect sent to:

```text
light.nyra_mansarda_nyra_status_ring
```

ESPHome must show the identity effect actually becoming active. No upstream `control_leds` phase write may overwrite it during the protected identity interval.

During actual TTS playback, purple must remain the visible owner until playback ends; a phase-5 `Wipe` must not replace it.

- [ ] **Step 5: Verify a second semantic transition after identity**

Confirm the latest queued Router processing state is restored only after the identity feedback window, proving the existing HA pending-state behavior still works after firmware arbitration.

- [ ] **Step 6: Final repository status and commit history check**

```bash
git status --short
git log --oneline -8
```

Expected: only intentional local/private ignored speaker files remain outside version control; no temporary diagnostics or uncommitted production changes.

- [ ] **Step 7: Push only after live verification succeeds**

```bash
git push
```

Do not declare the LED ownership fix complete until the physical interaction and logs satisfy Steps 3-5.
