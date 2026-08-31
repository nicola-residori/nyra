# Component Contract v1 --- Design

**Project:** N.Y.R.A. --- Neural sYstem for Reasoning & Automation\
**Status:** Approved design\
**Date:** 2026-08-31

## 1. Purpose and architecture

Component Contract v1 defines the boundaries and public contracts of the
first-level N.Y.R.A. components. The governing rule is: **N.Y.R.A. has a
common protocol, but not a universal payload.**

`nyra-router` is the central orchestrator and capability gateway.
First-level components do not communicate laterally; a component needing
a protected capability calls Router. Strictly private implementation
dependencies remain internal.

``` text
Home Assistant
      |
      v
 nyra-router
   |   |   |   |
   v   v   v   v
skills memory speaker-id llm

Component -> Router -> protected capability
```

Responsibilities:

-   **nyra-router:** request/session lifecycle, trusted RequestContext,
    identity resolution and continuity, routing, policy, capability
    mediation, HA Entity Resolver, interaction state, distributed
    correlation, central observability.
-   **nyra-skills:** deterministic action engine; first operational
    handler; deterministic/semantic interpretation;
    ExecutionPlan/Behavior construction and validation; ephemeral jobs;
    mandatory action gate for LLM-proposed actions.
-   **nyra-memory:** deterministic Operational Context plus advisory
    Semantic Long-Term Memory.
-   **nyra-llm:** inference only: prompts, provider/model selection,
    structured output, retries/fallback; typed SEMANTIC, REASONING and
    MEMORY_EXTRACTION purposes.
-   **nyra-speaker-id:** two independent areas: biometric Speaker
    Identification and Wake Word Dataset collection. No STT, TTS,
    playback, LED, session, wake-word runtime or training ownership.
-   **nyra-admin:** UI/observability/management only; never reads
    another component's DB/filesystem directly.

## 2. Common Service Protocol

Functional APIs use `/v1/...`. Backward-compatible additions remain v1;
breaking changes use a new path version. No negotiation/handshake in v1.

Service-to-service authentication is intentionally **not implemented in
v1**. v1 assumes a trusted private network. No placeholder auth
abstraction is required.

Every first-level service exposes:

``` text
GET /health
GET /ready
```

`/health` means process/HTTP alive. `/ready` means essential work can
currently be performed and may return a stable reason such as
`MODEL_UNAVAILABLE`.

Functional outcomes live in typed response bodies. Common outcomes where
applicable:

``` text
SUCCESS
DENIED
NOT_FOUND
AMBIGUOUS
UNAVAILABLE
FAILED
UNSUPPORTED
UNKNOWN_OUTCOME
```

HTTP 4xx/5xx is reserved for protocol, transport, validation, routing,
or unhandled server failures. Common errors remain small: stable `code`,
optional diagnostic `message`, optional structured `details`.

## 3. RequestContext and distributed correlation

Canonical IDs:

``` text
session_id = ses_<UUIDv4>
request_id = req_<UUIDv4>
trace_id   = trc_<UUIDv4>
span_id    = CT#operation#<8 uppercase alphanumeric>
```

For trusted HA ingress, HA creates `session_id` and `request_id`; Router
creates `trace_id`. Each component creates its own `span_id` for each
operation.

Clarification: same session/request, new trace. New intent: same
session, new request/trace.

Router owns authoritative RequestContext: session, request, trace, type,
language, source, area, resolved identity, temporal context, operational
context, policy context, optional clarification context, lifecycle
state. Components receive only fields required by their typed contract.

Minimum distributed correlation:

``` text
request_id?
origin_request_id?
trace_id
parent_span_id
typed payload
```

Interactive work normally has `request_id`. Delayed user-originated
activity may have null `request_id` and populated `origin_request_id`.
System activity may have both null.

**Every operation creates its own `span_id`.** REQUEST, intermediate
EVENT/DEBUG/WARN, and RESPONSE or FAULT logs belonging to that one
operation share its span ID. Different operations have different span
IDs. Distributed operations share `trace_id` and form a hierarchy
through `parent_span_id`.

A search by `session_id` in Admin MUST reconstruct the complete
distributed activity across all involved components.
Router/observability may enrich component logs with session correlation
before persistence. Async activity is linked through
`origin_request_id`.

## 4. Skills and operational execution

Router invokes Skills first. Outcomes:

``` text
HANDLED
MISS
NEEDS_CLARIFICATION
FAILED
```

Only `MISS` permits automatic fallback to reasoning LLM. `FAILED` does
not. Router owns pending clarification state; Skills remains
conversation-stateless.

Router knows `nyra-skills`, never individual Skill modules. A private
registry deterministically dispatches statically deployed v1 Skill
modules using stable skill metadata.

Skills may request semantic interpretation through Router -\>
`nyra-llm`. `SemanticResult` describes understanding, not execution or
authorization. It contains semantic intent/domain, actions with semantic
targets and generic parameters, optional temporal information, triggers,
conditions, confidence and interpretation. It contains no HA entity IDs
or native HA payloads.

`ExecutionPlan` is N.Y.R.A.'s operational representation. It may
originate from Skills or be proposed by reasoning LLM. LLM plans are
always proposed/untrusted. Plans may contain immediate execution steps
with conditions/dependencies and future `behaviors[]`.

Reasoning action flow:

``` text
Skills -> MISS
Router -> reasoning LLM
LLM -> response + proposed ExecutionPlan?
Router -> Skills
Skills -> validate / resolve / materialize / execute
Router -> protected capability
```

LLM never has side-effect capability.

Router owns HA entity resolution. Skills supplies semantic reference,
expected Nyra resource type and cardinality. For `ONE`: one match
RESOLVED, multiple AMBIGUOUS, zero NOT_FOUND. `MANY` must be explicitly
requested by Skills. Policy filters discovery. A resolved target remains
stable for the execution; Router never silently substitutes another
entity.

Step outcomes:

``` text
COMPLETED
FAILED
SKIPPED_DEPENDENCY
SKIPPED_CONDITION
```

Dependencies form an acyclic graph. Independent branches may continue.
No distributed transaction/global rollback in v1. Overall execution may
be COMPLETED or PARTIALLY_COMPLETED.

## 5. Behavior and Home Assistant runtime

Skills decides runtime destination. Strictly short-lived interaction
work may be a Skills job. Future, scheduled, recurring or event-driven
house behavior becomes a Home Assistant automation. There is no
arbitrary duration threshold.

Platform-independent Behavior:

``` text
Behavior
- behavior_id
- lifecycle: ONE_SHOT | PERSISTENT
- triggers[]      # OR
- conditions[]    # AND
- actions[]       # sequential
```

Actions support ACTION, DELAY and WAIT_CONDITION. WAIT_CONDITION timeout
is optional and never invented; default `on_timeout=STOP` unless the
user explicitly requests continuation.

For Nyra-managed ONE_SHOT automation: WAITING -\> RUNNING; success -\>
physically DELETE; failure -\> KEEP with observable error.

Nyra-created automations are `managed_by=NYRA`. Nyra may
inspect/control/modify/delete them. Manual HA automations are
discoverable/readable but completely non-controllable by Nyra, including
execution. Manual edits do not remove Nyra ownership from a Nyra-managed
automation; Nyra reads current HA config before modification.

A probable equivalent manual automation prevents silent duplication and
causes NEEDS_CLARIFICATION.

## 6. Capability Gateway

Capabilities use typed endpoints, not a universal capability endpoint.
Examples:

``` text
POST /v1/capabilities/home-assistant/resolve
POST /v1/capabilities/home-assistant/execute
POST /v1/capabilities/home-assistant/automations/create
POST /v1/capabilities/llm/semantic
```

Components do not provide authoritative caller/user/policy/source/area
data. Router recovers trusted context from correlation. In v1 this trust
boundary relies on the documented trusted private network.

Components use Nyra operations rather than native HA services:

``` text
TURN_ON TURN_OFF OPEN CLOSE TOGGLE SET
INCREASE DECREASE START STOP TRIGGER
```

with Nyra resource types such as LIGHT, SWITCH, COVER, CLIMATE,
MEDIA_PLAYER, SCRIPT, SCENE, AUTOMATION. Only Router's HA adapter
translates them. No raw HA-service escape hatch.

Skills validates semantic compatibility. Router revalidates existence,
availability, supported operation and current policy immediately before
side effects.

Conceptually idempotent operations include TURN_ON/OFF, OPEN/CLOSE,
SET(X). TOGGLE, INCREASE, DECREASE and TRIGGER are non-idempotent.
Uncertain non-idempotent execution returns UNKNOWN_OUTCOME and is not
blindly retried.

## 7. Skill Jobs

Skills may persist strictly ephemeral jobs. Lifecycle:

``` text
SCHEDULED -> CANCELLED
SCHEDULED -> RUNNING -> COMPLETED | FAILED | STOPPED | UNKNOWN_OUTCOME
```

CANCEL prevents start; STOP terminates an active effect when supported.
Scheduled jobs survive restart and overdue jobs run ASAP with delay
observable. A job found RUNNING after restart becomes UNKNOWN_OUTCOME
rather than being blindly re-executed. Semantic retries are not
performed at Skills level.

## 8. Memory Contract

Memory has two distinct domains/APIs: deterministic Operational Context
and advisory Semantic Memory.

Operational types v1: ALIAS, MAPPING, DEFAULT, SHORTCUT. SHORTCUT is
declarative intent expansion only: no arbitrary code, loops, HTTP, raw
HA services, LLM prompts or direct capabilities. Scope precedence: USER
\> FAMILY \> SYSTEM. Same-scope conflicts are AMBIGUOUS.
Natural-language management is interpreted by Skills and authorized by
Router before structured Memory operations.

Semantic Memory scopes: USER, FAMILY, SYSTEM. USER uses the same
canonical user identity used by N.Y.R.A., currently originating from HA.
Initial types: FACT, PREFERENCE, NOTE, RELATION. Initial sources:
USER_EXPLICIT, IMPORTED, SYSTEM. No inferred persistent memories in v1.

Lifecycle:

``` text
ACTIVE
SUPERSEDED
DELETED
```

Supersession preserves history. Deletion physically removes content,
embedding and sensitive metadata, leaving only a minimal tombstone. No
semantic-memory TTL.

All high-level writes pass through Router. `MEMORY_EXTRACTION` produces
advisory candidates only from useful information explicitly stated by
the user; it must not infer unstated preferences. Router decides
admission/scope/policy and NEW, DUPLICATE or SUPERSEDES. DUPLICATE may
update `last_confirmed_at`.

Explicit "remember" persistence is synchronous and confirmed only after
storage. Implicit useful explicit statements may be extracted
asynchronously with a new trace, null request ID and `origin_request_id`
pointing to the original request.

Semantic similarity alone never authorizes destructive mutation. One
unambiguous match may be modified/deleted; multiple plausible matches
require clarification; none returns NOT_FOUND.

## 9. LLM Contract

`nyra-llm` exposes typed SEMANTIC, REASONING and MEMORY_EXTRACTION
purposes. Router/Skills do not know provider/model names.

SEMANTIC is stateless and has no capability loop, HA access, entity
resolution or side effects.

REASONING outcomes:

``` text
COMPLETED
NEEDS_CAPABILITY
FAILED
```

COMPLETED may include response text and an optional proposed
ExecutionPlan. No chain-of-thought is exposed or persisted.

Reasoning may request only Router-controlled read-only capabilities such
as READ_STATE, READ_ATTRIBUTE and DISCOVER_RESOURCES. Router owns
round-trip budget, timeout and policy. Normal read failures may be
returned to LLM as structured results. Side-effect requests or
budget/timeout violations terminate the loop.

LLM may hold an ephemeral `reasoning_id` bound to one trace; it is not
conversation state and is deleted on completion/failure/timeout/budget
exhaustion.

Provider/model fallback remains internal to LLM and occurs only for
technical/contract failures, not low confidence or dissatisfaction with
a valid result.

Technical LLM observability may include purpose, provider, model,
attempt, fallback flag, latency, token counts, structured-output
validity and reasoning_id. No chain-of-thought.

## 10. Speaker Identification

Speaker ID owns canonical audio preprocessing: decode, canonical format,
cleanup, trim, validation. Exact sample rate/bit depth are
implementation choices. Only processed/trimmed audio is persisted; raw
input is not retained. Useful metadata includes original/final duration,
preprocessing version, format and quality. Invalid samples return
REJECTED with structured reason and are not stored.

`SpeakerProfile` is keyed by canonical `user_id`. Speaker ID does not
create global users. There is no ENROLLING/READY lifecycle:

``` text
0 valid samples -> no SpeakerProfile
1+ valid samples -> immediately usable SpeakerProfile
```

The user chooses how many enrollment samples to provide from the HA
dashboard.

Enrollment is functionally atomic:

``` text
receive -> preprocess/validate -> persist sample
-> update/rebuild biometric profile -> SUCCESS
```

SUCCESS only after the profile is usable.

Enrollment samples are permanent/no TTL, playable and individually
physically deletable from Admin. Deletion rebuilds the profile; deleting
the last sample deletes the profile. Admin can delete an entire profile,
physically deleting all enrollment audio, biometric model/data and
profile metadata while leaving the canonical user untouched.

Identification always compares against all profiles. Presence, area,
device or contextual probability never restrict candidates. Speaker ID
owns thresholds and classification:

``` text
IDENTIFIED
NOT_RECOGNIZED
FAILED
```

Zero profiles returns NOT_RECOGNIZED. Scores/candidates are diagnostic
only; Router never reinterprets them.

Router identity resolution:

``` text
IDENTIFIED(user_id)
-> user_id / SPEAKER_IDENTIFICATION

NOT_RECOGNIZED or FAILED
-> previous certainly identified user in SAME session?
   yes -> previous user / SESSION_CONTINUITY
   no  -> GUEST / GUEST_FALLBACK
```

Continuity never crosses sessions.

Speaker ID temporarily stores processed identification audio and all
candidate scores for diagnostics. Default configurable audio TTL:

``` text
IDENTIFIED       -> 1 hour
NOT_RECOGNIZED   -> 24 hours
FAILED           -> 24 hours
```

Expiration physically deletes audio. The technical record may remain for
general observability retention. Admin may listen and manually delete
audio while preserving the record. `identified_user_id` records only the
biometric result, never Router continuity resolution.

## 11. Wake Word Dataset

Wake Word Dataset is independent from Speaker Identification. It
collects cleaned **positive** wake-word samples for later external use
such as Colab. Negative samples are generated separately/automatically.
It does not own wake-word runtime or training.

`WakeWordRecordingSession` groups collection history. `WakeWordSample`
stores sample ID, recording session, wake word, processed audio path,
timestamp, device/speaker metadata, recorded-by metadata, audio metadata
and preprocessing metadata.

`recorded_by` and speaker/device are descriptive metadata only. There is
**no foreign key, ownership, lifecycle, or functional relationship**
between wake-word samples and SpeakerProfile. Changes/deletion in either
subsystem have zero effect on the other.

Wake-word samples are permanent until explicitly deleted.

Admin can list/filter/listen/select/delete samples, visually show
speaker/device and recorded-by tags, and export all or arbitrary
selected samples. Export is produced through Speaker ID APIs and
conceptually contains `audio/*.wav` plus `metadata.json`.
RecordingSession is a useful grouping, not an export boundary.

## 12. Device presentation

Speaker-ID outcomes are structured results only:

``` text
Speaker ID -> Router -> Home Assistant -> ESPHome satellite
```

ESPHome maps state to LEDs and local sounds. No satellite ACK handshake
is required in v1. HA creates speaker session IDs; Router may mark the
interaction closed and send a terminal state without waiting for an ACK.

## 13. Failure, resilience and retention

Distinct outcomes remain distinct: MISS != FAILED, NOT_FOUND != FAILED,
NOT_RECOGNIZED != FAILED, DENIED != FAILED.

Retries occur only when semantically safe. Non-idempotent uncertain
outcomes are not blindly retried.

Router remains an intentional central dependency/SPOF in v1;
clustering/failover is out of scope. It must remain lightweight, async
and robust.

General historical observability retention has one configurable default:

``` text
NYRA_RETENTION_DAYS = 30
```

It applies to logs, traces, spans, request/session observability,
terminal SkillJob history, execution results, faults and diagnostic
metadata needed to reconstruct an execution. Active operational records
are not removed by this retention.

Audio uses its domain-specific TTL/lifecycle. Semantic Memory, active
automations, SpeakerProfiles, EnrollmentSamples and WakeWordSamples
follow their own lifecycle.

## 14. Observability and Nyra Admin

Components use the shared N.Y.R.A. logging protocol. Important payloads
are structured JSON. Common fields include timestamp, CT, level, kind,
sessionId, requestId, traceId, spanId, parentSpanId, originRequestId,
event, operation, result and elapsed timings.

Timestamps are stored UTC and rendered by Admin in the browser's local
timezone.

Central redaction masks at least authorization, token, api_key,
password, secret and cookie as `***REDACTED***`. Audio is never embedded
in logs.

Admin supports navigation/filtering across session, request, trace, span
and component. A session search exposes complete distributed execution.

### Diagnostic export

Admin MUST export diagnostics at both **session** and **request** level.

Session export includes all requests, traces, spans, logs, faults and
relevant originated asynchronous activity correlated with the selected
session.

Request export includes all traces/spans for the selected request,
including multiple traces caused by clarification and relevant activity
correlated through `origin_request_id`.

Conceptual archive:

``` text
nyra-diagnostics-<session-or-request>.zip
- summary.json
- logs.json
- logs.txt
- traces.json
- metadata.json
```

The same redaction rules apply to exports. Diagnostic export does not
automatically include audio/binary domain artifacts.

## 15. Testing and Definition of Done

Public contracts require contract tests plus internal tests. Tests must
work without a real home, AI provider or biometric engine through
replaceable fakes such as FakeHA, FakeLLM, FakeMemoryBackend and
FakeBiometricEngine.

Critical invariants include:

-   only Skills MISS permits automatic reasoning fallback;
-   LLM plans cannot bypass Skills;
-   side effects cannot bypass Router;
-   ambiguous singular entity resolution requires clarification;
-   policy-filtered resources are not leaked;
-   uncertain non-idempotent operations are not blindly retried;
-   manual HA automations are non-controllable;
-   Operational Context is deterministic and Semantic Memory advisory;
-   destructive memory mutation requires unambiguous identification;
-   zero SpeakerProfiles returns NOT_RECOGNIZED;
-   Speaker-ID scores cannot override classification;
-   identity continuity is same-session only;
-   successful enrollment produces a usable profile;
-   deleting the last enrollment sample removes the profile;
-   Wake Word Dataset lifecycle is independent from SpeakerProfile;
-   session lookup reconstructs all participating component logs/spans.

A component is migrated only after:

``` text
contract defined
-> contract tests pass
-> service tests pass
-> reproducible bootstrap/deployment
-> fresh CT created from repository
-> /health OK
-> /ready OK
-> Router integration works
-> distributed logging works
-> Admin reconstructs execution
-> real end-to-end scenario works
```

Only then is its alpha implementation considered replaced.

## 16. Explicit v1 non-goals

-   service-to-service authentication or mTLS;
-   distributed Router HA/failover;
-   dynamic runtime Skill code installation;
-   automatic generated-Skill lifecycle;
-   raw HA service passthrough;
-   global distributed transactions/rollback;
-   arbitrary Behavior boolean-expression engine;
-   wake-word training;
-   manual negative wake-word collection;
-   Speaker-ID ownership of STT/TTS/playback;
-   chain-of-thought storage/exposure.
