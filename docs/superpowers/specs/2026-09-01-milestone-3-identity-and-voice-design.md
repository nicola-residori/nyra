# Milestone 3 — Identity and Voice — Design

**Project:** N.Y.R.A. — Neural sYstem for Reasoning & Automation
**Status:** Approved design
**Date:** 2026-09-01
**Baseline:** `main`, with Milestone 1 and Milestone 2 complete
**Primary specialist service:** `nyra-speaker-id`

## 1. Purpose

Milestone 3 adds production speaker identification and wake-word dataset collection to the Nyra v1 architecture without weakening the architectural boundaries established by Milestones 1 and 2.

The design preserves these invariants:

- Router remains the central trusted orchestration, context, identity-resolution, policy, capability, and observability boundary.
- Home Assistant remains a thin platform adapter.
- First-level services communicate only through Router.
- `source_id` identifies the physical/logical source of a request and never implies human identity.
- `nyra-speaker-id` performs biometric inference and wake-word dataset operations; it does not own trusted identity context, conversation continuity, policy, STT, TTS, playback, LED behavior, wake-word runtime, or wake-word training.
- Existing M2 speaker states, event transport, and device presentation remain the single interaction-state path.
- The previous `nyra-voice` implementation is a functional reference only. M3 deliberately preserves, moves, replaces, or retires each useful capability rather than copying the old service.

Milestone 3 is complete only after automated contract/integration tests, reproducible deployment on a fresh CT, and a small set of real hardware smoke tests all pass.

## 2. Architectural placement

The physical speaker continues to enter Nyra through Home Assistant.

```text
ESPHome speaker
      |
      | one microphone recording / same PCM samples
      |
      +---------------------> Home Assistant Assist path
      |                           |
      |                           +-> normal STT / Assist processing
      |
      +---------------------> Home Assistant Nyra audio ingress
                                  |
                                  v
                              nyra-router
                                  |
                                  v
                          nyra-speaker-id
```

There is no direct `Speaker -> nyra-speaker-id` path.

The speaker duplicates the same microphone samples toward two Home Assistant destinations because Home Assistant Core does not expose a clean public extension point that lets the Nyra custom integration duplicate the ESPHome Assist audio stream while retaining reliable source correlation. M3 therefore does not patch or monkey-patch Home Assistant Core.

This duplication is a tee of one capture, not two independent recordings.

## 3. Component ownership

### 3.1 Router

Router owns:

- request/session lifecycle;
- authoritative trusted `RequestContext`;
- source metadata;
- trusted identity resolution;
- same-session identity continuity;
- Guest fallback;
- identity-sensitive policy boundaries;
- identification timeout and timeout behavior;
- enrollment session orchestration;
- wake-word capture session orchestration;
- Router-facing admin APIs;
- distributed tracing and central observability;
- semantic interaction states propagated through the existing M2 event path.

Router never performs biometric scoring and never reinterprets Speaker-ID thresholds, margins, or classifications.

### 3.2 `nyra-speaker-id`

`nyra-speaker-id` owns two independent domains:

1. **Speaker Identification**
   - canonical audio preprocessing;
   - biometric embeddings;
   - speaker profiles;
   - enrollment samples;
   - all-profile comparison;
   - classification into `IDENTIFIED`, `NOT_RECOGNIZED`, or `FAILED`;
   - temporary identification diagnostics;
   - threshold and margin configuration.

2. **Wake Word Dataset**
   - positive processed wake-word sample storage;
   - wake-word grouping;
   - metadata;
   - playback/download data APIs;
   - deletion;
   - `.tar.gz` export.

It does not own:

- STT;
- TTS;
- playback orchestration;
- LED logic;
- conversation sessions;
- trusted identity continuity;
- Guest policy;
- wake-word runtime;
- wake-word training;
- global user creation.

### 3.3 Home Assistant

Home Assistant owns platform integration only:

- existing conversation ingress/egress;
- the additional Nyra audio ingress from ESPHome;
- authenticated HA user context for user-driven enrollment and wake-word capture;
- UI/card entry points for those user-driven procedures;
- forwarding Router semantic state to the speaker through the existing M2 bridge.

Home Assistant does not perform biometric inference or duplicate Router policy.

### 3.4 Nyra Admin

Nyra Admin remains an administrative/observability UI and never reads `nyra-speaker-id` storage directly. It accesses all specialist data through Router APIs.

## 4. Audio streaming contract

### 4.1 General model

Identification, enrollment, and wake-word capture use realtime streaming rather than buffering the complete recording in Home Assistant.

Each recording has a globally unique `audio_stream_id`. `source_id` must never be reused as the stream identifier.

The conceptual stream lifecycle is:

```text
START(metadata)
BINARY AUDIO CHUNKS...
END
```

The initial implementation should use a streaming transport appropriate for bidirectional lifecycle signaling, with WebSocket as the preferred design direction.

### 4.2 Stream purposes

Every stream has exactly one purpose:

```text
IDENTIFICATION
ENROLLMENT
WAKE_WORD_CAPTURE
```

### 4.3 START metadata

Common metadata includes, as applicable:

- `audio_stream_id`;
- purpose;
- `source_id`;
- `language`;
- `request_id`;
- `trace_id`;
- `parent_span_id`;
- conversation `session_id` when relevant.

Purpose-specific correlation uses typed identifiers rather than a generic operation session:

- identification: `request_id`;
- enrollment: `enrollment_session_id`, canonical authenticated `user_id`;
- wake-word capture: `wake_word_session_id`, authenticated `user_id`, wake-word text.

### 4.4 Correlation scope

M3 deliberately avoids persistent semantic audio-to-transcript mapping. Audio exists primarily for speaker identification and dataset operations.

The required correlation is only enough to guarantee that the correct biometric outcome is attached to the correct request/source/session under concurrency.

### 4.5 Interrupted streams

A stream that begins but never receives a valid terminal condition must not remain active indefinitely.

Connection loss, stream timeout, malformed sequence, or equivalent protocol failure produces a typed technical failure and cleans temporary state/files.

Late chunks, unknown stream IDs, duplicate END, and chunks after closure are rejected deterministically and tested.

## 5. Wire audio and canonical preprocessing

The wire format should match the natural ESPHome microphone output wherever practical. The internal canonical preprocessing format belongs to `nyra-speaker-id` and may differ from the wire format.

`nyra-speaker-id` owns:

- decode;
- channel canonicalization;
- resampling;
- normalization;
- VAD / speech gating;
- trimming;
- duration validation;
- RMS/peak/clipping/SNR and related quality metadata;
- model-minimum padding where required;
- preprocessing versioning.

Exact sample rate, bit depth, thresholds, and low-level DSP parameters are implementation details to be selected and tested during implementation. They are not normal Admin calibration sliders unless explicitly promoted to operational configuration later.

Raw input audio is never persisted. Only processed/trimmed audio may be persisted according to the domain lifecycle below.

### 5.1 Short-audio requirement

M3 must preserve the useful behavior learned from the legacy service: short but valid speech must remain identifiable.

Padding performed solely to satisfy the biometric model's minimum input length:

- is allowed;
- does not count as real speech duration;
- does not improve quality metrics artificially;
- must not cause otherwise invalid audio to pass an enrollment quality gate.

Enrollment uses a stricter quality gate. Identification is more permissive: if audio is technically usable, Speaker-ID attempts inference and lets threshold/margin determine recognition. Only genuinely unusable input becomes `FAILED`.

## 6. Biometric engine

### 6.1 M3 engine

M3 uses the ECAPA-TDNN / SpeechBrain approach proven useful in the legacy service.

For every usable identification recording:

```text
processed audio
    -> ECAPA embedding
    -> cosine similarity against every SpeakerProfile
    -> ordered candidate scores
    -> best score + second-best score
    -> threshold + margin classification
```

Context, area, presence, source device, or prior probability must never restrict the candidate set.

### 6.2 Classification

M3 uses one global threshold and one global best-vs-second margin.

A speaker is identified only when:

```text
best_score >= threshold
AND
(best_score - second_best_score) >= margin
```

Otherwise a successful biometric analysis returns `NOT_RECOGNIZED`.

Zero profiles also returns `NOT_RECOGNIZED`.

Technical/model/input failure returns `FAILED`.

Speaker-ID never returns `Guest`.

### 6.3 Outcomes

Minimal realtime decision payloads are intentionally small.

`IDENTIFIED` carries at least:

- `identified_user_id`;
- `best_score`;
- `diagnostic_id`;
- correlation/tracing fields.

`NOT_RECOGNIZED` carries at least:

- optional `best_score`;
- `diagnostic_id`;
- correlation/tracing fields.

`FAILED` carries at least:

- stable `reason_code`;
- optional `diagnostic_id` if a diagnostic record exists;
- correlation/tracing fields.

The full candidate matrix is not part of normal Router `RequestContext` and does not travel through the ordinary conversation path.

## 7. Trusted identity resolution and continuity

Router maintains the authoritative identity context.

Each conversation session may contain:

```text
last_trusted_user_id
```

This value is updated every time a new `IDENTIFIED(user_id)` result is received.

Resolution rules:

```text
IDENTIFIED(user_id)
-> user_id / SPEAKER_IDENTIFICATION
-> update last_trusted_user_id

NOT_RECOGNIZED | FAILED | identification timeout
-> last_trusted_user_id exists?
   yes -> same user / SESSION_CONTINUITY
   no  -> GUEST / GUEST_FALLBACK
```

Continuity never crosses session boundaries.

Continuity follows the **last certainly/biometrically identified user in the current session**, not merely the person who started the session.

Example:

```text
IDENTIFIED Nicola
NOT_RECOGNIZED -> Nicola
FAILED         -> Nicola
IDENTIFIED Alice
NOT_RECOGNIZED -> Alice
```

For normal identity-aware policy in M3, `SESSION_CONTINUITY` is treated as the same trusted person as the last biometric identification. Provenance remains observable but does not create a lower authorization tier.

## 8. Identification timeout

Identification is important and should not be discarded by an arbitrarily aggressive timeout.

The timeout is:

- owned by Router;
- persistent;
- configurable from Nyra Admin;
- editable at runtime without process restart;
- snapshotted at the start of each identification operation.

M3 starts with a deliberately conservative/high bootstrap timeout. The exact bootstrap value is an implementation configuration choice, not a design-time performance claim.

Operational metrics must include at least:

- p50 latency;
- p95 latency;
- p99 latency;
- timeout rate;
- late-result rate.

After real production data is collected, the timeout should be manually retuned using observed p95 plus a safety margin.

A result arriving after Router has already resolved the request must not retroactively change that request's trusted identity.

## 9. Runtime configuration

### 9.1 Speaker-ID configuration

`nyra-speaker-id` persistently owns:

- global biometric `threshold`;
- global biometric `margin`.

### 9.2 Router configuration

Router persistently owns:

- identification timeout.

### 9.3 Runtime semantics

Admin changes are realtime and require no restart.

Configuration is snapshotted per operation:

```text
operation A starts with threshold=.40
Admin changes threshold to .45
operation A completes with .40
operation B starts with .45
```

The same rule applies to margin and timeout.

Diagnostics must retain the effective configuration values used for the corresponding identification so historical outcomes remain explainable after later configuration changes.

Restart must preserve the configured values.

## 10. Enrollment model

### 10.1 Identity of the enrolled user

Enrollment starts only from Home Assistant.

The canonical user being enrolled is the authenticated HA user who starts the procedure. Speaker Identification is never used to infer who is being enrolled.

The user selects the physical Nyra speaker that will capture the voice.

### 10.2 Session semantics

Router owns enrollment sessions.

A session is created with a target valid-sample count selected by the user; six is the intended default UX value, not a biometric engine invariant.

A session is born once, produces zero or more accepted permanent samples, and terminates exactly once:

```text
COMPLETED
```

when the target is reached, or:

```text
TERMINATED(reason)
```

when cancelled, disconnected, or otherwise ended before completion.

A terminated session is never resumed. Already accepted samples remain permanent and immediately usable. Continuing later requires a new enrollment session.

### 10.3 Prompt generation

Enrollment uses pre-generated diverse phrases. The intended default mix for six samples is approximately:

- two short;
- two medium;
- two long.

The mix is a UX/calibration guide rather than a hard biometric-engine rule.

An LLM may generate randomized phrases constrained by language and length category to reduce lexical overfitting. There is no fixed canonical phrase set.

If the LLM is unavailable, the fallback must still be localized and deterministic for the requested language; it must not be an Italian-only hardcoded list.

### 10.4 Enrollment attempt

Each attempt uses a new `audio_stream_id`.

Speaker-ID returns one of:

```text
ACCEPTED
REJECTED
FAILED
```

`ACCEPTED` includes at least:

- `sample_id`;
- `profile_user_id`;
- processed duration;
- quality metadata.

`REJECTED` contains a stable reason code and useful quality metadata. Rejected audio is not stored as an enrollment sample and the accepted count does not increase.

`FAILED` represents technical/protocol/model failure.

Router owns the target N and accepted count; Speaker-ID does not.

## 11. Speaker profiles

A `SpeakerProfile` is keyed by canonical `user_id`.

Lifecycle:

```text
0 valid samples -> no profile
1+ valid samples -> profile immediately usable
```

Each accepted enrollment sample is permanent until explicit deletion and contains its processed audio plus its embedding and metadata.

The M3 profile representation is the equal-weight centroid of all valid enrollment embeddings for that user.

Quality weighting is explicitly deferred. Bad samples should be rejected at enrollment rather than silently downweighted.

Adding or deleting samples rebuilds the profile automatically.

Deleting the final sample removes the biometric profile only; it never deletes the canonical Nyra/HA user.

Deleting a whole profile physically deletes all its enrollment sample audio, embeddings, derived profile data, and profile metadata while leaving the canonical user untouched.

Everyday identification audio is never automatically promoted into training/enrollment data.

## 12. Enrollment Home Assistant UX

The HA voice/profile card is user-facing, not a technical administration surface.

It exposes the authenticated user's own profile only.

Typical controls include:

- speaker selector;
- target sample count;
- authoritative spoken-language selector/value;
- create profile / add samples action;
- current phrase;
- accepted progress `X/N`;
- terminate/cancel action.

The exact UI implementation may evolve, but it must not expose embeddings, thresholds, candidate matrices, or other users.

For each attempt:

```text
show phrase
-> local BIP means recording active
-> reuse M2 LISTENING semantic state / existing LED mapping
-> capture
-> reuse existing M2 local/internal processing state / mapping
-> ACCEPTED: local OK cue + fixed green feedback
-> REJECTED: local KO cue + fixed red feedback, same phrase retried
```

There is no intermediate TTS.

On normal completion only, the speaker emits one localized, first-person or neutral conclusion such as the language-equivalent of “Your voice profile has been updated.” TTS uses the existing M2 `SPEAKING` lifecycle and its existing device presentation.

No new enrollment-specific LED state machine is introduced.

## 13. Language and assistant identity

`language` is an authoritative contract/session parameter for user-facing voice operations.

It governs:

- enrollment phrase generation;
- user-facing enrollment messages;
- localized rejection explanations;
- fallback phrases;
- completion TTS;
- wake-word sample metadata where relevant.

Backend/domain responses prefer stable semantic reason codes rather than localized prose.

The technical project name, wake word, assistant personality/name, and human identity are separate concepts.

User-facing responses must not assume the assistant is named “Nyra”. Prefer first-person or neutral phrasing. Existing M2 hardcoded Italian or assistant-name assumptions are technical debt to correct when encountered in the M3 flow, not patterns to copy.

This rule does not remove legitimate technical uses of `Nyra` from repository names, integration names, package names, logs, admin headings, or architectural documentation.

## 14. Wake Word Dataset capture

### 14.1 Entry point

Wake-word recording starts only from Home Assistant.

The HA capture card includes:

- an editable wake-word text input;
- speaker selector;
- language where applicable;
- current dataset sample count;
- a short general explanation encouraging variation in distance, position, tone, volume, ambient conditions, movement, and normal daily context;
- one capture action.

The wake-word field is intentionally editable. Entering a wake word not already present creates a new logical dataset naturally; no separate Admin pre-creation step is required.

### 14.2 One-attempt session

One wake-word capture procedure/session equals exactly one attempt and can create at most one permanent sample.

Outcome:

```text
ACCEPTED
REJECTED
FAILED
```

After any outcome the session terminates. Recording another sample requires starting another capture.

Device sequence reuses the M2 interaction-state path:

```text
BIP
-> LISTENING / existing M2 presentation
-> processing / existing M2 presentation
-> ACCEPTED: OK + green
or
-> REJECTED/FAILED: KO + red
-> end
```

There is no final TTS for wake-word capture.

### 14.3 Dataset grouping

Wake Word Dataset is independent from SpeakerProfile.

Its primary hierarchy is:

```text
WakeWord
  -> Samples[]
```

Each accepted sample includes at least:

- `sample_id`;
- wake-word value / wake-word dataset identity;
- authenticated `user_id` that recorded it;
- `source_id` / speaker metadata;
- `captured_at`;
- duration;
- processed audio path;
- quality metadata;
- preprocessing version;
- language metadata where applicable.

`user_id` is descriptive provenance from authenticated HA capture, not biometric identification.

Wake-word samples are permanent until explicit deletion and have no lifecycle relationship with SpeakerProfiles.

## 15. Wake Word Admin and export

Admin groups samples primarily by wake word and supports:

- newest-first listing;
- visible timestamp;
- audio playback;
- filter by user;
- filter by speaker/source;
- delete one;
- multi-select;
- select all current filtered results;
- delete selected;
- export selected;
- export all current filtered results.

Export scope is always one wake-word dataset at a time. Multiple wake words are never silently mixed in one automatic export.

The canonical export format is `.tar.gz`:

```text
<wake-word-export>.tar.gz
  metadata.json
  audio/
    <sample_id>.wav
    ...
```

Router resolves UI/filter semantics into an explicit sample-ID selection. `nyra-speaker-id` generates the archive and does not need to understand the UI concept of “all visible”.

## 16. Storage model

M3 uses SQLite for metadata/state and the filesystem for processed WAV files.

WAV audio is not stored as SQLite BLOBs.

### 16.1 Speaker samples

Conceptual fields include:

- `sample_id`;
- `user_id`;
- `source_id`;
- optional enrollment session correlation;
- `captured_at`;
- original/final duration metadata;
- processed audio path;
- embedding;
- quality metadata;
- preprocessing version;
- biometric model version.

Conceptual filesystem layout:

```text
data/speaker-profiles/<user_id>/samples/<sample_id>.wav
```

Samples are the authoritative source. Profile centroids are derived/rebuildable data.

### 16.2 Identification diagnostics

Use a diagnostic record plus a normalized child table for candidate scores.

Conceptual diagnostic fields include:

- `diagnostic_id`;
- `captured_at`;
- `source_id`;
- `request_id`;
- conversation `session_id` when available;
- outcome;
- biometric-only `identified_user_id`;
- best score;
- effective margin/threshold configuration;
- optional processed audio path;
- expiry timestamps;
- preprocessing/model versions;
- technical error code;
- tracing/correlation metadata.

Candidate rows contain:

- `diagnostic_id`;
- candidate `user_id`;
- score;
- rank.

Conceptual filesystem path:

```text
data/diagnostics/<diagnostic_id>.wav
```

### 16.3 Wake-word storage

Use wake-word dataset metadata plus wake-word sample rows. Processed audio is organized by wake-word identity on the filesystem. Samples remain permanent until explicit deletion.

### 16.4 Operational sessions

Enrollment sessions and wake-word capture sessions are Router-owned orchestration state. Speaker-ID samples may retain their session IDs only as correlation metadata.

## 17. Diagnostic retention

Speaker-ID owns cleanup of its temporary biometric artifacts.

Detailed identification diagnostics include processed audio and the complete candidate score matrix.

Approved M3 TTLs:

```text
IDENTIFIED       -> 15 minutes
NOT_RECOGNIZED   -> 24 hours
FAILED           -> 24 hours
```

If a failure occurs before usable processed audio exists, the diagnostic may contain no audio.

After detailed TTL expiry, Speaker-ID physically deletes:

- processed diagnostic audio;
- detailed candidate score rows.

A synthetic diagnostic record remains only according to Nyra's general observability retention policy. It must follow the same `NYRA_RETENTION_DAYS` policy rather than introducing an independent hardcoded history retention.

The synthetic record may retain:

- timestamp;
- source;
- outcome;
- biometric `identified_user_id` if any;
- best score if available;
- technical error;
- model/preprocessing versions;
- effective configuration;
- correlation identifiers.

It does not retain audio, embeddings, or the full candidate matrix after detailed expiry.

Manual deletion of diagnostic audio through Admin may remove the audio before TTL while preserving the synthetic record.

Speaker-ID cleanup also removes interrupted temporary stream files/state and is idempotent.

## 18. Admin diagnostics and profile management

### 18.1 Speaker Identification — Diagnostics

Default order is newest first.

Filters include at least:

- speaker/source;
- outcome;
- user.

List/detail presentation includes, while available:

- timestamp;
- speaker tag;
- outcome;
- green identified-user tag for `IDENTIFIED`;
- red presentation for `NOT_RECOGNIZED` and `FAILED`, while preserving distinct textual outcomes;
- best score;
- processed audio player;
- all candidate scores ranked in detail;
- model/preprocessing versions;
- request/diagnostic correlation.

After detailed TTL, Admin clearly indicates that audio and candidate scores have expired while retained synthetic fields remain available under normal log retention.

### 18.2 Speaker Identification — Profiles

Profiles are grouped primarily by canonical `user_id`; `source_id` is metadata only and never a biometric partition.

Samples are listed newest first with acquisition timestamp always visible.

Each sample supports audio playback, duration, speaker/source tag, and useful quality/preprocessing metadata.

Admin supports:

- list and inspect existing enrollment samples;
- delete one sample;
- multi-select;
- select all current filtered results;
- delete selected with one profile rebuild after the group operation;
- delete entire biometric profile.

Manual labeling or promotion of everyday diagnostic audio into enrollment is out of scope for M3.

### 18.3 Speaker Identification — Settings

Admin exposes at least:

- threshold;
- margin;
- identification timeout;
- current/default values;
- reset-to-default operations;
- concise explanations of effect.

Changes are realtime and persistent as defined in Section 9.

## 19. Observability

M3 extends existing distributed tracing rather than creating a voice-specific logging system.

Identity timeline must distinguish biometric completion from Router identity resolution.

Conceptual events:

```text
identity.started

identity.completed
  outcome=IDENTIFIED | NOT_RECOGNIZED | FAILED
  identified_user_id=?
  best_score=?
  diagnostic_id=?
  latency_ms=...

identity.resolved
  user_id=...
  resolution=SPEAKER_IDENTIFICATION | SESSION_CONTINUITY | GUEST_FALLBACK
```

This separation makes speaker changes and continuity decisions reconstructible.

General logs/timeline must never contain:

- audio bytes;
- biometric embeddings;
- full candidate score matrices.

Enrollment events include at least:

```text
enrollment.started
enrollment.capture.started
enrollment.sample.accepted
enrollment.sample.rejected
enrollment.completed
enrollment.terminated
```

Wake-word capture events include at least:

```text
wake_word.capture.started
wake_word.capture.accepted
wake_word.capture.rejected
wake_word.capture.failed
wake_word.capture.completed
```

Metrics include at least identification outcome rates, per-speaker rates, latency average/p50/p95/p99, timeout rate, and late-result rate.

## 20. Failure behavior

Speaker Identification runs in parallel with STT and must not become the single point that prevents an otherwise valid conversation from continuing.

Router may perform identity-independent work while biometric inference is in flight, but it must resolve trusted identity before crossing an identity-sensitive processing/policy boundary.

Failure cases:

- Speaker-ID unavailable -> `FAILED/SERVICE_UNAVAILABLE`, then Router continuity/Guest resolution;
- technically unusable audio -> `FAILED/INSUFFICIENT_AUDIO` or equivalent stable reason;
- processable but low-confidence audio -> `NOT_RECOGNIZED`;
- identification timeout -> Router continuity/Guest resolution;
- late biometric result -> diagnostic only; never retroactively changes resolved request identity.

A request is not automatically repeated solely because identification failed.

## 21. API families

HA and Admin never call `nyra-speaker-id` directly.

Router is the public/trusted boundary. The service follows Component Contract v1 conventions:

```text
GET /health
GET /ready
/v1/...
```

Conceptual specialist API families:

```text
/v1/identify/*
/v1/enrollment/*
/v1/wake-words/*
/v1/config/*
```

Admin-facing query APIs support typed filters such as user/source/from/to/limit/cursor with default newest-first ordering.

Exact endpoint names and DTO schemas are finalized in the implementation plan/code while preserving the behavioral contract in this design.

## 22. Legacy capability preservation matrix

| Legacy `nyra-voice` capability | M3 decision | Destination / rationale |
|---|---|---|
| ECAPA-TDNN / SpeechBrain | PRESERVE | `nyra-speaker-id` biometric engine |
| Embeddings | PRESERVE | `nyra-speaker-id` |
| Cosine similarity | PRESERVE | all-profile comparison |
| Global threshold | PRESERVE | runtime Speaker-ID config |
| Best-vs-second margin | PRESERVE | runtime Speaker-ID config |
| Centroid profile | PRESERVE | equal-weight centroid |
| Multi-sample enrollment | PRESERVE / REDESIGN | HA-driven Router session |
| Short-audio support | PRESERVE | required behavior |
| VAD / trim / resample / normalization | PRESERVE / REDESIGN | versioned preprocessing |
| RMS / peak / clipping / SNR metrics | PRESERVE | quality metadata/gates |
| Raw diagnostic audio retention | RETIRE | raw input is never persisted |
| Processed diagnostic audio | PRESERVE | 15m / 24h TTL |
| Full candidate scores | PRESERVE | temporary diagnostic detail only |
| `source_map` source->person cache | RETIRE | violates `source_id != identity` |
| `source_map` TTL continuity | RETIRE | Router owns session continuity |
| service returns `guest` | RETIRE | Speaker-ID returns typed biometric outcome only |
| direct speaker `/capture` | RETIRE | Speaker -> HA -> Router -> Speaker-ID |
| direct `/identify/raw` | RETIRE | new streaming contract |
| legacy `/identify` | REPLACE | typed v1 service contract |
| Wake Word Dataset | PRESERVE / REDESIGN | `nyra-speaker-id` independent domain |
| positive wake-word samples | PRESERVE | permanent dataset samples |
| per-wake-word organization | PRESERVE | primary dataset grouping |
| user/device metadata | PRESERVE / IMPROVE | authenticated user + source tags |
| internal HTML Dataset Manager | MOVE / RETIRE | HA user UX + Nyra Admin administration |
| listen/delete/select | MOVE / IMPROVE | Nyra Admin |
| ZIP wake-word export | REPLACE | `.tar.gz` + `metadata.json` |
| STT ownership | OUT OF SCOPE | existing HA Assist pipeline |
| TTS ownership | OUT OF SCOPE | existing pipeline |
| LED ownership | OUT OF SCOPE | Router/M2 semantic states + ESPHome presentation |
| session ownership | OUT OF SCOPE | Router |
| wake-word runtime/training | OUT OF SCOPE | ESPHome / external training workflow |

No new M3 component may depend on the old CT's filesystem, databases, manually placed model files, or source-to-person cache.

Legacy profile/dataset import, if ever required, is an explicit migration operation and not an architectural dependency.

## 23. Existing source-of-truth updates required

Implementation of this design requires coordinated documentation updates rather than a parallel contract.

At minimum:

1. **Component Contract v1 — Speaker Identification retention**
   - change `IDENTIFIED` detailed diagnostic TTL from 1 hour to 15 minutes;
   - keep `NOT_RECOGNIZED` and `FAILED` at 24 hours;
   - clarify that expiry removes both audio and detailed candidate scores;
   - retained synthetic diagnostic metadata follows the general Nyra observability retention policy.

2. **Component Contract v1 — continuity wording**
   - clarify that same-session continuity tracks the most recently certainly/biometrically identified user, and updates whenever a different user is later identified.

3. **Component Contract v1 — enrollment/identification outcome semantics**
   - clarify that enrollment quality rejection is `REJECTED`, while unusable identification input is a typed `FAILED` outcome and processable low-confidence input is `NOT_RECOGNIZED`.

4. **Component Contract v1 — Wake Word recording-session semantics**
   - replace the generic grouping interpretation with the M3 rule that one HA wake-word capture session is exactly one attempt and creates at most one permanent sample; another sample requires a new session.

5. **Architecture/roadmap terminology where needed**
   - use `nyra-speaker-id` for the M3 biometric/Wake Word specialist role;
   - avoid implying that this service owns generic STT/TTS “Voice” processing.

6. **M2 user-facing language debt**
   - M3-touched user-facing hardcoded Italian or assistant-name assumptions are corrected to follow authoritative `language` and personality-neutral wording.

## 24. Testing strategy

Most M3 validation is automated.

### 24.1 Unit/service tests

Cover at least:

- preprocessing transformations;
- short-audio padding semantics;
- enrollment quality rejection;
- identification processability vs failure;
- ECAPA adapter behavior behind a replaceable biometric interface;
- threshold + margin classification;
- zero-profile behavior;
- equal-weight centroid rebuild;
- add/delete/multi-delete/last-sample profile lifecycle;
- persistent config and snapshot semantics;
- diagnostic cleanup and idempotence;
- wake-word sample lifecycle and export.

### 24.2 Contract tests

Router <-> Speaker-ID contract tests use replaceable fakes and verify typed outcomes, correlation, failure mapping, and minimal realtime decision payloads.

Explicit identity-continuity tests include:

```text
IDENTIFIED Nicola
NOT_RECOGNIZED -> Nicola
FAILED         -> Nicola
timeout        -> Nicola
IDENTIFIED Alice
NOT_RECOGNIZED -> Alice

new session
NOT_RECOGNIZED -> Guest
```

### 24.3 Streaming/concurrency tests

Automated tests create multiple independent streams with different `source_id` and `audio_stream_id` values, interleave chunks, and verify no cross-stream contamination.

Test at least:

- concurrent different speakers;
- two rapid streams from the same `source_id`;
- START without END;
- disconnect mid-stream;
- duplicate END;
- unknown stream;
- post-close chunks;
- delayed Speaker-ID;
- Speaker-ID unavailable;
- timeout and late result.

Physical simultaneous people/speakers are not required for this concurrency proof.

### 24.4 Biometric regression fixtures

Use reproducible prerecorded audio fixtures where licensing/privacy permits to exercise real preprocessing/embedding/classification paths.

Personal recordings must not be committed to the public repository by default. Local E2E datasets or appropriately licensed public fixtures are acceptable.

### 24.5 Runtime configuration tests

Verify that an in-flight operation keeps its initial config snapshot while subsequent operations immediately use the newly persisted threshold, margin, or timeout. Verify persistence across restart.

### 24.6 Retention tests

Use a controlled clock.

Verify boundary behavior for:

```text
IDENTIFIED       14m59s -> detailed data present
IDENTIFIED       15m00s -> detailed data expired
NOT_RECOGNIZED   23h59m -> detailed data present
NOT_RECOGNIZED   24h00m -> detailed data expired
FAILED           23h59m -> detailed data present
FAILED           24h00m -> detailed data expired
```

Synthetic metadata follows the shared observability retention policy.

### 24.7 Enrollment tests

Test accepted/rejected retries, target completion, interruption, retained accepted samples, non-resumable terminated sessions, short valid samples, invalid samples, profile rebuild, and localized phrase/message flow.

### 24.8 Wake-word tests

Test one-attempt session semantics, accepted/rejected/failed outcomes, editable/new wake-word creation, grouping, filters, newest-first ordering, selection semantics, deletion, and `.tar.gz` contents.

### 24.9 Localization tests

At least two languages traverse real M3 user-facing flows during automated/integration testing. Tests ensure reason codes remain domain-level and that no M3 user-facing response depends on a hardcoded Italian string or a hardcoded assistant name.

## 25. Real hardware smoke tests

Manual E2E validation is intentionally small and practical.

It must prove at least:

- one real ESPHome speaker tees the same mic capture toward normal Assist and Nyra audio ingress without breaking normal Assist;
- one real authenticated user can create/update a speaker profile from HA;
- that user can be identified in normal speech;
- at least one short command remains identifiable/processable;
- a non-profile voice can produce `NOT_RECOGNIZED` rather than a false confident identity in at least one validation scenario;
- Wake Word capture stores a real sample;
- BIP/OK/KO and existing M2 semantic LED presentation occur correctly;
- final enrollment TTS uses the existing M2 speaking lifecycle;
- persisted profile/config/dataset survive a full relevant-component reboot.

Two people speaking simultaneously through two physical speakers are not a milestone requirement; concurrency is covered automatically with prerecorded/interleaved streams.

## 26. Reproducible deployment and migration gate

`nyra-speaker-id` is not considered migrated until the Component Contract v1 migration gate succeeds from repository state rather than the legacy CT.

Required sequence:

```text
contract updated
-> contract tests pass
-> service tests pass
-> reproducible bootstrap/deployment exists
-> fresh CT created from repository
-> model/dependencies provisioned reproducibly
-> database/schema initialized
-> /health OK
-> /ready OK
-> Router integration works
-> distributed logging works
-> Admin reconstructs identity activity
-> real hardware smoke scenario works
-> reboot persistence verified
```

Only then may the legacy `nyra-voice` implementation be considered replaced for M3.

## 27. M3 Definition of Done

Milestone 3 is DONE only when all of the following are true:

- `nyra-speaker-id` exists as the reproducible first-level specialist service defined here;
- Router remains the sole owner of trusted identity resolution, continuity, timeout, and policy;
- Home Assistant remains a thin adapter with the approved audio ingress/tee architecture and no HA Core patch;
- Speaker-ID compares every profile and returns only typed `IDENTIFIED`, `NOT_RECOGNIZED`, or `FAILED` biometric outcomes;
- short valid audio is supported;
- enrollment is HA-driven, authenticated-user-bound, multi-sample, permanent, and profile-rebuilding;
- wake-word capture is HA-driven, one-attempt-per-session, editable-wake-word, and stored independently from speaker profiles;
- Admin can manage profiles, diagnostics, settings, and Wake Word Dataset only through Router;
- threshold, margin, and identification timeout are persistent and realtime-configurable without restart, with per-operation snapshots;
- detailed diagnostic retention is 15 minutes for `IDENTIFIED` and 24 hours for `NOT_RECOGNIZED`/`FAILED`, with synthetic history following shared log retention;
- distributed observability separates biometric result from Router identity resolution and never places audio/embeddings/full candidate matrices in general logs;
- automated unit, contract, integration, streaming, concurrency, retention, configuration, localization, enrollment, and wake-word tests pass;
- fresh-CT deployment passes `/health`, `/ready`, Router integration, and observability reconstruction;
- practical real-speaker smoke tests pass, including reboot persistence;
- no M3 production path depends on the legacy `nyra-voice` service.

## 28. Explicit M3 non-goals

M3 does not add:

- Speaker-ID-owned STT or TTS;
- direct speaker-to-Speaker-ID networking;
- Home Assistant Core patches;
- biometric candidate restriction by presence/area/device/context;
- per-user thresholds;
- probabilistic/calibrated biometric classifier beyond threshold + margin;
- quality-weighted profile centroids;
- automatic use of normal conversation audio for training;
- manual labeling/promotion of diagnostics into enrollment;
- automatic threshold/timeout tuning;
- wake-word training;
- manual negative wake-word collection;
- resumable enrollment sessions;
- a second LED/session state system;
- cross-session identity continuity;
- separate policy treatment for biometric identity versus same-session continuity;
- a new heavy database platform;
- persistent audio-to-transcript alignment.
