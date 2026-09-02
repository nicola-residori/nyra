# Milestone 3 — Identity and Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Milestone 3 with Router-owned trusted identity resolution, a reproducible `nyra-speaker-id` service, parallel speaker identification, Home Assistant enrollment and Wake Word capture, runtime configuration, diagnostics, retention, and automated/E2E verification.

**Architecture:** Preserve the M1/M2 central-Router architecture. ESPHome sends the same microphone samples to normal HA Assist and a Nyra HA audio ingress; HA forwards Nyra audio to Router, and Router streams it to `nyra-speaker-id`. `nyra-speaker-id` owns biometric inference, profile/sample storage, preprocessing, diagnostic detail, and Wake Word datasets; Router owns request/session correlation, trusted identity continuity, timeout policy, presentation APIs, and protected policy.

**Tech Stack:** Python, FastAPI/Uvicorn, Pydantic, SQLite, filesystem WAV storage, SpeechBrain ECAPA-TDNN, PyTorch/torchaudio, Home Assistant custom integration, ESPHome YAML/C++, pytest, systemd.

**Spec:** `docs/superpowers/specs/2026-09-01-milestone-3-identity-and-voice-design.md`

## Global Constraints

- Router remains the central trusted orchestration/context/policy boundary.
- First-level services do not communicate laterally.
- Home Assistant remains a thin adapter.
- Speaker audio path is Speaker → HA → Router → `nyra-speaker-id`; never Speaker → `nyra-speaker-id`.
- `source_id` identifies a source and MUST NOT imply human identity.
- `nyra-speaker-id` returns only `IDENTIFIED`, `NOT_RECOGNIZED`, or `FAILED`; it never decides Guest.
- Session continuity uses the last certainly identified user in the current conversation session and never crosses sessions.
- Threshold and margin are global runtime configuration owned by `nyra-speaker-id`.
- Identification timeout is runtime configuration owned by Router.
- Runtime configuration changes require no restart and affect only operations started after the change.
- Raw microphone audio is never persisted by `nyra-speaker-id`.
- Detailed IDENTIFIED diagnostic audio/candidate scores expire after 15 minutes.
- Detailed NOT_RECOGNIZED/FAILED diagnostic audio/candidate scores expire after 24 hours.
- Synthetic diagnostic records follow Nyra's general log-retention policy.
- Enrollment samples and accepted Wake Word samples are permanent until explicit deletion.
- Enrollment is started only from Home Assistant and always enrolls the authenticated HA user.
- Wake Word capture is started only from Home Assistant; the Wake Word is user-editable text.
- A Wake Word capture session is one attempt and produces at most one permanent sample.
- User-facing language comes from the session/request `language`; no Italian-only business logic.
- Do not hardcode `Nyra` as the assistant's spoken/personality name.
- Reuse M2 semantic speaker states/LED feedback; do not create a parallel LED protocol.
- Existing `nyra-voice` is reference material only; do not make the new implementation depend on its runtime files/state.
- Follow Component Contract v1: `/health`, `/ready`, `/v1/...`, distributed correlation fields, reproducible fresh-CT bootstrap.
- TDD: every behavioral change starts with a failing test.
- No task is complete until its focused tests and the relevant regression suite pass.

---

## File/Component Map

The executor MUST first reconcile these planned paths with the current `main` tree. Existing M1/M2 modules keep their established names; do not rename working modules merely to match this plan.

- `docs/superpowers/specs/2026-08-31-component-contract-v1-design.md` — update M3 contract deltas (TTL, single-attempt WW session, runtime config semantics).
- `router/` — typed Speaker-ID client/port, audio-stream relay, identity continuity, timeout config, Admin-facing proxy APIs, events/metrics.
- `homeassistant/custom_components/nyra/` — Nyra audio ingress and M3 HA actions/entities/services required by cards; existing conversation adapter remains thin.
- `esphome/` — reusable common speaker package changes for microphone tee and local BIP/OK/KO cues while preserving M2 state colors.
- `speaker-id/` or the repository's chosen top-level service directory for `nyra-speaker-id` — new specialist service. Use the repository's established one-top-level-service convention; do not create a nested `app/` package solely for style.
- `admin/` — Speaker Identification profiles, diagnostics, settings, and Wake Word dataset views through Router only.
- `tests/` — unit, contract, integration, concurrency, retention, localization, and E2E harness tests.
- `deploy/` — reproducible `nyra-speaker-id` CT bootstrap/systemd/dependencies following existing Nyra service deployment patterns.

---

### Task 1: Freeze the M3 Contract Delta

**Files:**
- Modify: `docs/superpowers/specs/2026-08-31-component-contract-v1-design.md`
- Modify only if required by existing documentation conventions: `docs/DECISIONS.md`, `docs/ROADMAP.md`, `docs/state/CURRENT_STATE.md`
- Test: repository documentation/contract validation tests if present

**Interfaces:**
- Consumes: approved M3 design spec.
- Produces: authoritative documented contract used by every later task.

- [ ] **Step 1: Read the current contract and locate every Speaker-ID/Wake Word TTL/session/config statement**

Run:
```bash
cd /Users/nicola/Develop/nyra
grep -nE 'speaker-id|Speaker Identification|WakeWord|IDENTIFIED|NOT_RECOGNIZED|FAILED|TTL|threshold|margin|timeout' docs/superpowers/specs/2026-08-31-component-contract-v1-design.md
```

Expected: existing Speaker-ID and Wake Word contract clauses are identified before editing.

- [ ] **Step 2: Add a failing documentation/contract assertion**

If the repository already has documentation tests, extend them. Otherwise create `tests/contracts/test_m3_contract_docs.py` with assertions that the contract contains the approved invariants:

```python
from pathlib import Path

CONTRACT = Path("docs/superpowers/specs/2026-08-31-component-contract-v1-design.md")

def test_m3_contract_contains_approved_identity_retention():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "15 minutes" in text
    assert "24 hours" in text

def test_m3_contract_defines_single_attempt_wake_word_capture():
    text = CONTRACT.read_text(encoding="utf-8")
    assert "one attempt" in text.lower()
    assert "at most one" in text.lower()
```

- [ ] **Step 3: Run the focused test and verify failure**

Run:
```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/contracts/test_m3_contract_docs.py
```

Expected: FAIL because the old contract still carries the pre-M3 wording.

- [ ] **Step 4: Update the contract without duplicating architecture**

Make the existing clauses state explicitly:
- IDENTIFIED detailed diagnostics: 15 minutes.
- NOT_RECOGNIZED/FAILED detailed diagnostics: 24 hours.
- synthetic record retention: same policy as Nyra logs.
- Wake Word recording session: exactly one attempt, max one accepted sample.
- threshold/margin are Speaker-ID runtime config; Router timeout is Router runtime config.
- runtime values are snapshotted at operation start.
- Admin never starts enrollment/capture; HA does.

- [ ] **Step 5: Run contract tests**

Run:
```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/contracts/test_m3_contract_docs.py
git diff --check
```

Expected: PASS; no whitespace errors.

- [ ] **Step 6: Commit**

```bash
cd /Users/nicola/Develop/nyra
git add docs/superpowers/specs/2026-08-31-component-contract-v1-design.md tests/contracts/test_m3_contract_docs.py
git commit -m "docs: align component contract with M3 identity design"
```

---

### Task 2: Create the `nyra-speaker-id` Service Foundation

**Files:**
- Create: top-level `speaker-id/app.py` (or exact service path chosen after reconciling current tree)
- Create: `speaker-id/requirements.txt`
- Create: focused persistence/config modules only if `app.py` would otherwise mix unrelated responsibilities
- Create: `tests/speaker_id/test_health.py`
- Create: `tests/speaker_id/test_config.py`
- Modify/Create: matching `deploy/` bootstrap/systemd artifacts following existing service patterns

**Interfaces:**
- Produces: `/health`, `/ready`, persistent runtime config, SQLite initialization, filesystem data root.
- Config API:
  - `GET /v1/config`
  - `PUT /v1/config/identification`
  - returns `threshold`, `margin`, defaults/version metadata.
- Does not yet perform biometric inference.

- [ ] **Step 1: Write failing health/readiness/config tests**

Test expectations:
```python
def test_health_is_liveness(client):
    assert client.get("/health").status_code == 200

def test_ready_requires_initialized_storage_and_model_state(client):
    body = client.get("/ready").json()
    assert "ready" in body

def test_identification_config_persists_across_app_restart(app_factory, tmp_path):
    app = app_factory(tmp_path)
    app.client.put("/v1/config/identification", json={"threshold": 0.43, "margin": 0.09})
    app.close()

    restarted = app_factory(tmp_path)
    assert restarted.client.get("/v1/config").json()["identification"] == {
        "threshold": 0.43,
        "margin": 0.09,
    }
```

- [ ] **Step 2: Run focused tests and verify failure**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/speaker_id/test_health.py tests/speaker_id/test_config.py
```

Expected: FAIL because the service does not exist.

- [ ] **Step 3: Implement minimal service bootstrap and persistent config**

Use SQLite for operational config and metadata; filesystem paths must be under one service data root. Defaults are bootstrap values, not env-only operational state.

- [ ] **Step 4: Implement snapshot semantics**

Expose an internal immutable config snapshot object:
```python
@dataclass(frozen=True)
class IdentificationConfigSnapshot:
    threshold: float
    margin: float
    revision: int
```

Every future identify operation obtains one snapshot before processing.

- [ ] **Step 5: Run tests**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/speaker_id/test_health.py tests/speaker_id/test_config.py
git diff --check
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/nicola/Develop/nyra
git add speaker-id tests/speaker_id deploy
git commit -m "feat: bootstrap nyra speaker id service"
```

---

### Task 3: Implement Canonical Audio Preprocessing

**Files:**
- Create: focused preprocessing module under the chosen Speaker-ID service path
- Create: `tests/speaker_id/test_preprocessing.py`
- Add: small generated/non-personal audio fixtures under `tests/fixtures/audio/` when licensing permits

**Interfaces:**
- Produces:
```python
@dataclass(frozen=True)
class ProcessedAudio:
    wav_bytes: bytes
    sample_rate: int
    duration_seconds: float
    speech_seconds: float
    quality: AudioQuality
    preprocessing_version: str

def preprocess_audio(raw: bytes, *, mode: Literal["identification", "enrollment", "wake_word"]) -> ProcessedAudio
```
- Raw input is never persisted.
- Padding for model minimum duration does not increase `speech_seconds`.

- [ ] **Step 1: Write failing tests for mono/resample/trim/quality/short-audio semantics**

Include:
```python
def test_short_valid_identification_is_processable():
    result = preprocess_audio(short_valid_fixture, mode="identification")
    assert result.speech_seconds >= MIN_REAL_SPEECH_FOR_IDENTIFICATION

def test_model_padding_does_not_count_as_real_speech():
    result = preprocess_audio(short_valid_fixture, mode="identification")
    assert result.duration_seconds >= MODEL_MIN_SECONDS
    assert result.speech_seconds < result.duration_seconds

def test_bad_enrollment_audio_is_rejected():
    with pytest.raises(AudioRejected) as exc:
        preprocess_audio(low_signal_fixture, mode="enrollment")
    assert exc.value.reason_code == "LOW_SIGNAL"
```

- [ ] **Step 2: Run and verify failure**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/speaker_id/test_preprocessing.py
```

- [ ] **Step 3: Implement preprocessing using legacy lessons, not legacy runtime state**

Preserve useful behavior: canonical mono format, resampling, normalization, VAD/trim, duration, RMS/peak/clipping/SNR metadata, short-speech compatibility.

- [ ] **Step 4: Ensure enrollment gate is stricter than identification**

Identification attempts model inference whenever audio is technically processable; enrollment rejects poor samples before storage.

- [ ] **Step 5: Run tests and commit**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/speaker_id/test_preprocessing.py
git diff --check
git add speaker-id tests/speaker_id tests/fixtures/audio
git commit -m "feat: add speaker audio preprocessing"
```

---

### Task 4: Implement Profiles, Enrollment Samples, and ECAPA Embeddings

**Files:**
- Create/modify: Speaker-ID profile persistence and model modules
- Create: `tests/speaker_id/test_profiles.py`
- Create: `tests/speaker_id/test_enrollment.py`

**Interfaces:**
- `SpeakerProfile` keyed only by canonical `user_id`.
- Each accepted sample stores processed WAV + embedding + quality metadata.
- Profile centroid is equal-weight mean of all valid sample embeddings.
- `source_id` is metadata only.

- [ ] **Step 1: Write failing profile invariant tests**

Cover one-sample usability, add→rebuild, delete→rebuild, multi-delete→single rebuild, last sample→profile deletion, canonical user untouched.

- [ ] **Step 2: Run and verify failure**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/speaker_id/test_profiles.py tests/speaker_id/test_enrollment.py
```

- [ ] **Step 3: Implement ECAPA model adapter**

Wrap SpeechBrain behind a narrow interface:
```python
class SpeakerEmbeddingEngine(Protocol):
    def embed(self, audio: ProcessedAudio) -> list[float]: ...
```

Production adapter loads ECAPA-TDNN; tests use deterministic fake embeddings.

- [ ] **Step 4: Implement atomic accepted-sample transaction**

Sequence: preprocess → embed → persist processed WAV → persist metadata/embedding → rebuild centroid → return ACCEPTED. Roll back DB/file changes on failure.

- [ ] **Step 5: Run tests and commit**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/speaker_id/test_profiles.py tests/speaker_id/test_enrollment.py
git diff --check
git add speaker-id tests/speaker_id
git commit -m "feat: add speaker profiles and enrollment storage"
```

---

### Task 5: Implement Identification Classification and Diagnostics

**Files:**
- Create/modify: Speaker-ID identification/diagnostic modules
- Create: `tests/speaker_id/test_identification.py`
- Create: `tests/speaker_id/test_diagnostics.py`

**Interfaces:**
```python
class IdentificationOutcome(str, Enum):
    IDENTIFIED = "IDENTIFIED"
    NOT_RECOGNIZED = "NOT_RECOGNIZED"
    FAILED = "FAILED"
```

Minimal realtime result:
```python
@dataclass(frozen=True)
class IdentificationResult:
    outcome: IdentificationOutcome
    identified_user_id: str | None
    best_score: float | None
    diagnostic_id: str | None
    reason_code: str | None
```

Detailed candidate scores remain in Speaker-ID diagnostics.

- [ ] **Step 1: Write failing classifier tests**

Exact cases:
```python
@pytest.mark.parametrize(
    ("scores", "threshold", "margin", "expected"),
    [
        ({"a": .82, "b": .50}, .40, .07, "IDENTIFIED"),
        ({"a": .82, "b": .79}, .40, .07, "NOT_RECOGNIZED"),
        ({"a": .35, "b": .20}, .40, .07, "NOT_RECOGNIZED"),
        ({}, .40, .07, "NOT_RECOGNIZED"),
    ],
)
def test_classification(scores, threshold, margin, expected):
    ...
```

- [ ] **Step 2: Verify failure**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/speaker_id/test_identification.py tests/speaker_id/test_diagnostics.py
```

- [ ] **Step 3: Implement all-profile cosine comparison and threshold+margin**

Never filter candidates by source/area/presence.

- [ ] **Step 4: Persist detailed diagnostic record using the operation's config snapshot**

Store candidate rows normalized as `(diagnostic_id, user_id, score, rank)` and record preprocessing/model/config revisions.

- [ ] **Step 5: Run tests and commit**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/speaker_id/test_identification.py tests/speaker_id/test_diagnostics.py
git diff --check
git add speaker-id tests/speaker_id
git commit -m "feat: add speaker identification and diagnostics"
```

---

### Task 6: Implement Diagnostic Retention and Housekeeping

**Files:**
- Modify: Speaker-ID diagnostics/storage modules
- Create: `tests/speaker_id/test_retention.py`

**Interfaces:**
- IDENTIFIED detail expiry: 15 minutes.
- NOT_RECOGNIZED/FAILED detail expiry: 24 hours.
- Cleanup removes processed diagnostic WAV and candidate rows.
- Synthetic record remains until general Nyra log retention expires.

- [ ] **Step 1: Write clock-controlled failing tests**

Test boundaries at `14:59/15:00` and `23:59/24:00`; include idempotent repeated cleanup and orphan temp-file cleanup.

- [ ] **Step 2: Verify failure**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/speaker_id/test_retention.py
```

- [ ] **Step 3: Implement deterministic housekeeping service**

Inject clock in tests; do not use sleep-based tests.

- [ ] **Step 4: Run tests and commit**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/speaker_id/test_retention.py
git diff --check
git add speaker-id tests/speaker_id
git commit -m "feat: enforce speaker diagnostic retention"
```

---

### Task 7: Implement Wake Word Dataset Storage and Export

**Files:**
- Create/modify: Speaker-ID Wake Word modules/endpoints
- Create: `tests/speaker_id/test_wake_words.py`
- Create: `tests/speaker_id/test_wake_word_export.py`

**Interfaces:**
- One capture session = one attempt = max one accepted sample.
- Dataset primary key/group is normalized Wake Word identity while retaining user-entered display text as required by spec.
- Accepted samples permanently store processed WAV.
- Export input is explicit sample IDs resolved by Router.
- Output is `.tar.gz` with `metadata.json` and `audio/<sample_id>.wav`.

- [ ] **Step 1: Write failing capture/storage tests**

Cover ACCEPTED, REJECTED, FAILED, arbitrary new Wake Word text, user/source/language/timestamp metadata, newest-first query.

- [ ] **Step 2: Write failing tar export test**

Use Python `tarfile` to assert exact members and metadata/sample-ID match.

- [ ] **Step 3: Run and verify failure**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/speaker_id/test_wake_words.py tests/speaker_id/test_wake_word_export.py
```

- [ ] **Step 4: Implement storage/query/delete/export**

Speaker-ID receives explicit IDs; it must not implement UI semantics such as “all visible”.

- [ ] **Step 5: Run tests and commit**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/speaker_id/test_wake_words.py tests/speaker_id/test_wake_word_export.py
git diff --check
git add speaker-id tests/speaker_id
git commit -m "feat: add wake word dataset management"
```

---

### Task 8: Define and Implement Router ↔ Speaker-ID Typed Client Contract

**Files:**
- Modify: existing Router SpeakerIdentityPort/client modules
- Create/modify: shared DTOs according to current repository conventions
- Create: `tests/router/test_speaker_identity_client.py`
- Create: contract tests between Router fake server and Speaker-ID

**Interfaces:**
- Router receives only minimal realtime decision fields.
- Admin detail calls can retrieve full candidate scores through Router.
- Correlation includes `audio_stream_id`, request/session IDs, source ID, trace/span fields.

- [ ] **Step 1: Replace string/None placeholder expectations with typed failing tests**

Assert `IDENTIFIED`, `NOT_RECOGNIZED`, `FAILED` DTO parsing and no `"guest"` service outcome.

- [ ] **Step 2: Verify failure**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/router/test_speaker_identity_client.py
```

- [ ] **Step 3: Implement typed port/client without identity policy**

The client transports Speaker-ID decisions. It must not decide continuity/Guest or recalculate scores.

- [ ] **Step 4: Run tests and commit**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/router/test_speaker_identity_client.py
git diff --check
git add router shared tests/router
git commit -m "feat: add typed speaker identity contract"
```

---

### Task 9: Implement Router Identity Continuity and Runtime Timeout

**Files:**
- Modify: existing Router lifecycle/session/request-context modules
- Modify: Router operational config persistence/API
- Create: `tests/router/test_identity_continuity.py`
- Create: `tests/router/test_identity_timeout.py`
- Create: `tests/router/test_identity_config.py`

**Interfaces:**
- Session state includes `last_trusted_user_id`.
- `IDENTIFIED(user)` updates it.
- NOT_RECOGNIZED/FAILED/timeout resolve to it if present; otherwise Guest.
- Timeout snapshot is taken when identification starts.
- Late result cannot mutate resolved request identity.

- [ ] **Step 1: Write failing continuity sequence test**

Sequence must assert:
`Nicola IDENTIFIED → uncertain → Nicola → Alice IDENTIFIED → uncertain → Alice`, then new session uncertain → Guest.

- [ ] **Step 2: Write failing timeout snapshot/late-result tests**

Change Admin timeout while request A is in flight; A keeps old timeout, request B uses new timeout.

- [ ] **Step 3: Verify failure**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/router/test_identity_continuity.py tests/router/test_identity_timeout.py tests/router/test_identity_config.py
```

- [ ] **Step 4: Implement continuity and timeout at the identity-sensitive policy boundary**

Allow identity-independent parallel work, but resolve TrustedIdentityContext before protected/identity-sensitive processing.

- [ ] **Step 5: Run tests and commit**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/router/test_identity_continuity.py tests/router/test_identity_timeout.py tests/router/test_identity_config.py
git diff --check
git add router tests/router
git commit -m "feat: resolve trusted speaker identity in router"
```

---

### Task 10: Implement Realtime Audio Streaming Router Relay

**Files:**
- Create/modify: Router audio streaming endpoint/session registry
- Modify: Speaker-ID streaming endpoint
- Create: `tests/router/test_audio_streaming.py`
- Create: `tests/integration/test_audio_stream_concurrency.py`

**Interfaces:**
- Lifecycle: START metadata → binary chunks → END.
- `audio_stream_id` is globally unique for active streams.
- Purpose is one of `IDENTIFICATION`, `ENROLLMENT`, `WAKE_WORD_CAPTURE`.
- Identification maps stream → request.
- Enrollment/Wake Word use their typed operation session IDs.
- START without END eventually fails and cleans temporary state.

- [ ] **Step 1: Write failing stream lifecycle tests**

Cover unknown ID, duplicate START, chunk after close, duplicate END, disconnect, timeout.

- [ ] **Step 2: Write failing interleaved concurrency test**

Interleave chunks for source A/audio_stream A and source B/audio_stream B; assert bytes and results never cross.

- [ ] **Step 3: Verify failure**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/router/test_audio_streaming.py tests/integration/test_audio_stream_concurrency.py
```

- [ ] **Step 4: Implement streaming relay with bounded temporary state**

Router relays; it does not preprocess or persist audio.

- [ ] **Step 5: Run tests and commit**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/router/test_audio_streaming.py tests/integration/test_audio_stream_concurrency.py
git diff --check
git add router speaker-id tests/router tests/integration
git commit -m "feat: stream speaker audio through router"
```

---

### Task 11: Add Home Assistant Nyra Audio Ingress

**Files:**
- Modify/create focused modules under `homeassistant/custom_components/nyra/`
- Modify integration manifest/services only as required by established HA patterns
- Create: HA adapter tests under existing `tests/homeassistant/`

**Interfaces:**
- Receives the second copy of ESPHome microphone samples.
- Associates source/session/request metadata available from the Nyra integration.
- Streams to Router; never calls Speaker-ID directly.
- Existing HA Assist path remains unchanged.

- [ ] **Step 1: Write failing HA ingress tests**

Assert audio goes only to Router client and that `source_id` remains source metadata, never trusted identity.

- [ ] **Step 2: Verify failure using the repository's HA test command**

Run the focused HA test module according to existing M2 test conventions.

- [ ] **Step 3: Implement minimal ingress and Router streaming client**

Do not monkey-patch HA Core or intercept private ESPHome internals.

- [ ] **Step 4: Run focused HA tests plus existing M2 conversation tests**

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/nicola/Develop/nyra
git add homeassistant tests/homeassistant
git commit -m "feat: add home assistant nyra audio ingress"
```

---

### Task 12: Add Reusable ESPHome Microphone Tee and Local Cues

**Files:**
- Modify: reusable common speaker configuration under `esphome/`
- Modify: versioned local speaker assets if BIP/OK/KO files are required
- Add/modify: ESPHome validation tests/scripts already used by M2

**Interfaces:**
- One microphone capture, same samples to HA Assist and HA Nyra ingress.
- No direct Speaker-ID endpoint/configuration on speaker.
- Existing M2 semantic LED states remain authoritative.
- Local cues: BIP recording active, OK accepted, KO rejected/failed.

- [ ] **Step 1: Add a failing configuration/static validation**

Assert common provisioning contains both HA destinations and no `nyra-speaker-id` address.

- [ ] **Step 2: Compile/validate one existing physical speaker config before implementation**

Record baseline command/output using the same ESPHome tooling as M2.

- [ ] **Step 3: Implement tee once in shared provisioning**

New speakers must inherit it through instance parameters; do not duplicate logic per speaker.

- [ ] **Step 4: Compile/validate representative speaker configs**

Expected: existing Assist behavior remains valid and new Nyra audio path compiles.

- [ ] **Step 5: Commit**

```bash
cd /Users/nicola/Develop/nyra
git add esphome tests
git commit -m "feat: tee speaker audio to nyra ingress"
```

---

### Task 13: Implement Router-Owned Enrollment Sessions

**Files:**
- Modify/create: Router enrollment session/orchestration API
- Modify: Speaker-ID enrollment endpoint/client
- Create: `tests/router/test_enrollment_sessions.py`
- Create: `tests/integration/test_enrollment_flow.py`

**Interfaces:**
- Authenticated HA user is immutable `profile_user_id`.
- Router owns target N, accepted count, phrase sequence, session status.
- Session terminates exactly once: `COMPLETED` or `TERMINATED(reason)`.
- Accepted samples survive termination.
- Rejected attempt repeats same phrase and does not increment accepted count.

- [ ] **Step 1: Write failing state-machine tests**

Cover 6/6 with reject/retry and 4/6 termination preserving four samples.

- [ ] **Step 2: Verify failure**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/router/test_enrollment_sessions.py tests/integration/test_enrollment_flow.py
```

- [ ] **Step 3: Implement phrase-plan contract**

Represent generated phrases as typed items with `text`, `language`, and length class `SHORT|MEDIUM|LONG`; default six-plan is 2/2/2.

- [ ] **Step 4: Implement LLM generation adapter plus localized deterministic fallback**

No Italian-only fallback and no assistant-name hardcoding.

- [ ] **Step 5: Run tests and commit**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/router/test_enrollment_sessions.py tests/integration/test_enrollment_flow.py
git diff --check
git add router speaker-id tests
git commit -m "feat: orchestrate speaker enrollment sessions"
```

---

### Task 14: Implement HA Enrollment UX

**Files:**
- Modify/create: HA Nyra services/entities/card/dashboard artifacts according to the repository's existing M2 UI pattern
- Add: translations under `homeassistant/custom_components/nyra/translations/`
- Add: HA tests for authenticated-user binding, language, speaker selection, count, reason localization

**Interfaces:**
- HA only; Admin cannot start enrollment.
- Inputs: speaker, sample count, voice language.
- Shows one phrase, X/N progress, terminate action.
- Intermediate feedback uses semantic states + BIP/OK/KO.
- Completion triggers one localized neutral/first-person TTS sentence.

- [ ] **Step 1: Write failing HA tests for user binding and localization**

Attempt to supply another user ID must be ignored/rejected; canonical target is authenticated HA user.

- [ ] **Step 2: Implement minimal HA-facing orchestration calls**

Keep business state in Router.

- [ ] **Step 3: Add localized messages/reason-code mapping**

Test at least `it-IT` and `en-US`.

- [ ] **Step 4: Run HA regression tests and commit**

```bash
cd /Users/nicola/Develop/nyra
git add homeassistant tests/homeassistant
git commit -m "feat: add home assistant voice enrollment"
```

---

### Task 15: Implement Router-Owned Wake Word Capture and HA UX

**Files:**
- Modify/create: Router Wake Word capture session API
- Modify/create: HA Wake Word capture UI/service
- Add: translations/tests
- Create: `tests/router/test_wake_word_capture.py`
- Create: `tests/integration/test_wake_word_capture_flow.py`

**Interfaces:**
- Inputs: editable Wake Word text, speaker, language.
- Authenticated HA user becomes sample `user_id`.
- Exactly one audio attempt.
- ACCEPTED/REJECTED/FAILED all terminate session.
- No final TTS.

- [ ] **Step 1: Write failing single-attempt tests**

Assert second attempt on same session is rejected and arbitrary new WW text creates/targets a distinct dataset.

- [ ] **Step 2: Verify failure**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/router/test_wake_word_capture.py tests/integration/test_wake_word_capture_flow.py
```

- [ ] **Step 3: Implement Router session and HA action**

General HA explanation encourages natural variation; do not generate per-sample “near/far” instructions.

- [ ] **Step 4: Run tests and commit**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/router/test_wake_word_capture.py tests/integration/test_wake_word_capture_flow.py
git diff --check
git add router homeassistant tests
git commit -m "feat: add wake word capture flow"
```

---

### Task 16: Add Router Admin APIs for Profiles, Diagnostics, Wake Words, and Settings

**Files:**
- Modify/create: Router Admin-facing API modules
- Modify: Speaker-ID query/delete/export/config endpoints
- Create: `tests/router/test_speaker_id_admin_api.py`

**Interfaces:**
- Admin → Router only.
- Profiles: list users/samples, listen, delete one/many, delete profile.
- Diagnostics: filters source/outcome/user/time/cursor; detail fetches candidate scores/audio while available.
- Wake Words: list/filter/listen/delete/export.
- Settings: Speaker-ID threshold/margin and Router timeout through one Admin-facing surface.
- “Select all visible” is resolved by Router/UI to explicit sample IDs before export/delete.

- [ ] **Step 1: Write failing proxy/policy/filter tests**

Assert Router never exposes a direct Speaker-ID URL and preserves newest-first/cursor semantics.

- [ ] **Step 2: Verify failure**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/router/test_speaker_id_admin_api.py
```

- [ ] **Step 3: Implement APIs with explicit DTOs**

Do not put candidate matrices into normal RequestContext/log APIs.

- [ ] **Step 4: Run tests and commit**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/router/test_speaker_id_admin_api.py
git diff --check
git add router speaker-id tests/router
git commit -m "feat: expose speaker identity admin APIs"
```

---

### Task 17: Implement Nyra Admin M3 Views

**Files:**
- Modify/create: focused components/pages under current `admin/` structure
- Add: frontend tests following existing Admin test tooling

**Interfaces:**
- Profiles page: canonical user grouping; newest samples first; timestamp, player, duration, source tag, quality; single/multi-delete.
- Diagnostics page: newest first; filters Speaker/Outcome/User; best score; temporary audio; detail candidate ranking; expired-detail state.
- Settings page: threshold, margin, timeout, defaults/reset; save applies realtime.
- Wake Word page: dataset by WW; filters; player; delete; filtered select-all; `.tar.gz` export.
- No enrollment/capture start controls in Admin.

- [ ] **Step 1: Write failing view/API interaction tests**

Include explicit test that Admin has no “start enrollment” or “start capture” action.

- [ ] **Step 2: Implement Profiles and Diagnostics views**

Use Router APIs only.

- [ ] **Step 3: Implement Settings and Wake Word views**

Settings save must show success only after Router confirms persistence.

- [ ] **Step 4: Run Admin tests/build and commit**

Use the existing Admin test/build commands from `admin/package.json`/repository docs; do not invent a second frontend toolchain.

```bash
cd /Users/nicola/Develop/nyra
git add admin
git commit -m "feat: add speaker identity admin views"
```

---

### Task 18: Add Identity Observability and Metrics

**Files:**
- Modify: Router lifecycle/event/metrics modules
- Create: `tests/router/test_identity_observability.py`

**Interfaces:**
Events:
- `identity.started`
- `identity.completed` with biometric outcome, identified user if biometric, best score, diagnostic ID, latency.
- `identity.resolved` with final user and resolution provenance.
Enrollment/Wake Word events per design.
Metrics include outcome rates, per-speaker rates, latency avg/p50/p95, timeout rate, late-result rate.

- [ ] **Step 1: Write failing event-sequence tests**

Assert NOT_RECOGNIZED followed by SESSION_CONTINUITY produces separate completed/resolved events.

- [ ] **Step 2: Write failing privacy test**

General logs/events must not contain audio bytes, embeddings, or `candidate_scores`.

- [ ] **Step 3: Implement events/metrics**

Reuse M1/M2 observability infrastructure.

- [ ] **Step 4: Run tests and commit**

```bash
cd /Users/nicola/Develop/nyra
pytest -q tests/router/test_identity_observability.py
git diff --check
git add router tests/router
git commit -m "feat: add speaker identity observability"
```

---

### Task 19: Add Automated Regression, Concurrency, Failure, and Localization Suite

**Files:**
- Create/modify: `tests/integration/` M3 suite
- Add: permitted/reproducible audio fixtures or fixture-generation instructions
- Modify: CI configuration if the repository has one

**Interfaces:**
- No physical two-person/two-speaker requirement.
- Concurrency uses recorded/generated streams and deterministic fake embeddings where biometric truth is not under test.
- Real ECAPA regression uses legally usable fixtures and is separately marked if model download/runtime makes it expensive.

- [ ] **Step 1: Add end-to-end simulated request tests**

Cover:
- identified user;
- unknown→Guest in fresh session;
- continuity;
- user switch;
- short phrase;
- service unavailable;
- timeout and late result;
- realtime config snapshot;
- enrollment reject/retry/terminate;
- Wake Word accepted/rejected/failed;
- two interleaved speakers.

- [ ] **Step 2: Add localization invariant tests**

At least `it-IT` and `en-US`; scan user-facing response fixtures for forbidden hardcoded assistant-name assumptions.

- [ ] **Step 3: Run full automated suite**

Use the repository's established full-test command. Also run:
```bash
cd /Users/nicola/Develop/nyra
git diff --check
```

Expected: all M1/M2/M3 regressions PASS.

- [ ] **Step 4: Commit**

```bash
cd /Users/nicola/Develop/nyra
git add tests
git commit -m "test: cover M3 identity and voice flows"
```

---

### Task 20: Make `nyra-speaker-id` Reproducible on a Fresh CT

**Files:**
- Modify/create: `deploy/` bootstrap/systemd files
- Modify: service README/operations docs following repository conventions
- Modify: `docs/state/CURRENT_STATE.md` only after verification

**Interfaces:**
- Fresh Debian 12 CT can be built from repository.
- Service layout follows existing Nyra CT convention.
- No dependency on legacy `nyra-voice` files.
- Model acquisition/cache behavior is documented and readiness reflects actual availability.

- [ ] **Step 1: Write/extend bootstrap verification script**

It must check service user/layout convention, Python dependencies, model readiness, DB/data directories, systemd enable/start, `/health`, `/ready`.

- [ ] **Step 2: Execute on a fresh CT**

Do not reuse the legacy CT as proof of reproducibility.

- [ ] **Step 3: Verify Router integration and distributed trace from the fresh CT**

Expected: Router can stream identification audio and receive typed result.

- [ ] **Step 4: Reboot the CT and verify persistence**

Threshold/margin, profiles, Wake Word dataset, DB schema, and service startup survive reboot.

- [ ] **Step 5: Commit deployment/docs**

```bash
cd /Users/nicola/Develop/nyra
git add deploy docs
git commit -m "ops: add reproducible speaker id deployment"
```

---

### Task 21: Perform Minimal Physical E2E and Retire M3 Legacy Paths

**Files:**
- Modify: `docs/state/CURRENT_STATE.md`
- Modify: `README.md`, `ROADMAP.md`, and ADR/architecture docs only where milestone state/legacy status actually changes
- Remove/disable any obsolete M3 legacy routing discovered during implementation only after replacement is verified

**Interfaces:**
- Physical smoke tests validate hardware boundary, not impossible concurrency scenarios.
- Legacy `nyra-voice` is no longer required by any M3 path.

- [ ] **Step 1: Run physical speaker smoke test**

Verify one real speaker:
wake word → HA Assist + Nyra audio tee → Router → Speaker-ID → TrustedIdentityContext → normal response → TTS/speaker.

- [ ] **Step 2: Run real enrollment smoke test**

From HA: choose speaker/language/count; include short/medium/long phrases; verify at least one accepted sample and normal completion; verify BIP/OK/KO/state feedback.

- [ ] **Step 3: Run real identification smoke tests**

Verify enrolled speaker recognition, a short command, and one unknown voice yielding NOT_RECOGNIZED rather than a false positive where practical.

- [ ] **Step 4: Run real Wake Word capture smoke test**

Use editable WW text, capture one sample, verify Admin visibility and `.tar.gz` export.

- [ ] **Step 5: Reboot involved components and repeat a minimal recognition**

Verify persistence and startup ordering.

- [ ] **Step 6: Prove legacy independence**

Stop the old `nyra-voice` service/CT and repeat the minimal M3 path. No M3 request may depend on it.

- [ ] **Step 7: Update milestone documentation**

Mark M3 complete only after all automatic tests, fresh-CT verification, and physical smoke tests pass. Record measured p50/p95/p99 and the initial timeout calibration decision; do not tune blindly before data exists.

- [ ] **Step 8: Run final verification**

```bash
cd /Users/nicola/Develop/nyra
git status
git diff --check
```

Run the repository's complete test suite, HA tests, Admin tests/build, ESPHome representative compile, `/health`, `/ready`, and fresh-CT verification.

Expected: all PASS; working tree contains only intentional milestone-documentation changes.

- [ ] **Step 9: Commit milestone completion**

```bash
cd /Users/nicola/Develop/nyra
git add README.md ROADMAP.md docs
git commit -m "docs: mark M3 identity and voice complete"
```

---

## Plan Self-Review

### Spec coverage

The plan covers:
- Router trust boundary and no lateral service communication.
- Speaker audio tee through HA and Router.
- typed Speaker-ID outcomes and all-profile ECAPA classification.
- threshold+margin and runtime snapshot semantics.
- Router timeout, p95-oriented later calibration, timeout/late-result metrics.
- session-scoped last-certainly-identified continuity.
- enrollment ownership, phrases, short-audio behavior, profile rebuild/delete.
- Wake Word editable text, one-attempt capture, permanent dataset, `.tar.gz` export.
- SQLite + filesystem storage.
- diagnostic TTL and synthetic retention.
- Admin-only management through Router.
- localization/personality invariants.
- M2 speaker state reuse.
- automated concurrency/failure tests and minimal physical smoke tests.
- fresh CT reproducibility and legacy independence.

### Placeholder scan

No `TBD`, `TODO`, “implement later”, or unspecified “write tests” steps are permitted. Where exact file names depend on current repository layout, the plan explicitly requires reconciliation with the existing M1/M2 path rather than inventing a competing module name.

### Type/interface consistency

- Speaker-ID owns `IdentificationConfigSnapshot(threshold, margin, revision)`.
- Router separately snapshots identification timeout.
- Speaker-ID realtime result never carries Guest or Router continuity.
- `audio_stream_id` is distinct from `source_id`.
- Enrollment and Wake Word operation session IDs are distinct from conversation session IDs.
- Full candidate scores remain diagnostic detail, not normal RequestContext.

### Execution rule

Do not execute this plan directly on `main`. At implementation time create an isolated worktree using the Superpowers worktree workflow, then execute task-by-task with TDD and review gates.
