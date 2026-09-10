# Nyra Current State

## Version

Nyra v1.0-dev

## Current milestone

Milestone 2 — Home Assistant adapter and Nyra speaker integration — is complete.

Milestone 3 — Identity and Voice — is complete. Speaker-ID, physical
enrollment, identity validation, wake-word sample capture/export, trusted Home
Assistant user-name enrichment, Nyra Admin identity management, observability,
automated regression coverage, and fresh-CT reproducibility are deployed and
verified.

Milestone 4 — Memory and Context — is complete and deployed in production.

Milestone 5 — Skills — is complete and deployed in production.

The production M5 implementation uses a dedicated deterministic `nyra-skills`
service behind the Router trust boundary. Skills receives trusted context and
correlation from Router, never Home Assistant credentials. Router owns Home
Assistant resolution/execution and Nyra-managed automation capabilities.
Deterministic Home Assistant actions, target clarification, restart-safe
ephemeral jobs, persistent Behaviors, explicit Memory management Skills,
Router-backed Admin diagnostics, and distributed Router/Skills/capability
observability are deployed and physically verified.


The production M4 implementation includes a dedicated SQLite/WAL Memory service,
typed operational and semantic contracts, deterministic USER → FAMILY → SYSTEM
resolution, identity-isolated semantic search using the local
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` embedding provider,
explicit confirm/supersede/delete lifecycle, and privacy-safe correlated
observability. Router has a bounded Memory client, dependency readiness,
conditional NONE/OPTIONAL/REQUIRED enrichment, and authenticated management
routes. Nyra Admin provides separate operational-context and semantic-memory
pages with Home Assistant display names plus stable IDs, filters, similarity
scores, revisions, and exact-ID mutations.

The deployment uses reproducible Debian 12 systemd/bootstrap/verification assets,
persistent SQLite storage and model cache, consistent backup, guarded restore,
and rollback procedures. Memory runs in dedicated CT `105`; Router and Admin
consume it through the private service endpoint. Home Assistant, ESPHome, and
Speaker-ID required no M4 production changes.

## Implemented foundation

- Router and Admin observability foundation
- canonical correlation IDs: `ses_<UUID>`, `req_<UUID>`, `trc_<UUID>`
- nullable session/request IDs for job traces
- synchronous `POST /v1/requests`
- persisted clarification state with new trace per continuation
- authoritative `closed` result and `SESSION_CLOSED` event
- Router-owned speaker identity initiation boundary and identity outcomes
- Memory / Skill Check / Skill Execution / LLM interaction-state boundaries
- persistent `WS /v1/events` with authentication, subscriptions, heartbeat, reconnect-compatible state resynchronization
- lifecycle observability
- shared Component Contract v1 protocol primitives
- Router `/health` and `/ready` standardized on shared service status contracts
- central observability reconstructs authoritative session correlation from `request_id` / `origin_request_id`

## Milestone 2 implemented

- native Home Assistant `nyra` conversation adapter as a thin Router boundary
- Home Assistant adapter carries a synchronized `shared.protocol` runtime fallback so protocol types keep one canonical Python module identity
- synchronous Router ingress through `POST /v1/requests`
- source and conversation metadata propagation
- `ha_assist` authenticated Home Assistant user context
- `ha_speaker` source kept separate from personal identity
- stable ESPHome `source_id` propagation and exact speaker lookup
- read-only `Nyra Source ID` diagnostic entity
- authenticated Router event stream bridged through Home Assistant to ESPHome
- real-time semantic speaker interaction states
- protected two-blink identity feedback
- actual announcement lifecycle owns SPEAKING while preserving identity transients
- session-close sound and visual feedback
- canonical local `Nyra IT` and `Nyra EN` micro-wake-word models, selectable through Home Assistant with the stock base wake-word models replaced
- physical path validated: wake word -> ESPHome -> Home Assistant -> Router -> Home Assistant -> TTS/speaker

## Deployment

- `nyra-memory`: CT `105`, `192.168.0.13`, port `8090`
- `nyra-skills`: dedicated Debian 12 CT/service, port `8090`
- `nyra-router`: CT `108`, `192.168.0.16`, port `8090`
- `nyra-admin`: CT `108`, `192.168.0.16`, port `80`
- `nyra-speaker-id`: CT `106`, `192.168.0.14`, port `8090`

The Memory container is a fresh Debian 12 deployment built by

`deploy/bootstrap/memory.sh`. It runs as the locked `nyra-memory` service
account, persists SQLite/WAL state under `/var/lib/nyra-memory`, and caches the
multilingual embedding model under persistent storage. CT105 was rebuilt with
the authorized VMID/IP (`105`, `192.168.0.13`) and verified before and after
reboot with `deploy/verify/memory.sh`; the saved persistence snapshot remained
valid across the restart.

The initial Linux bootstrap exposed an unnecessary CUDA/NVIDIA dependency pull
through PyTorch. Production was corrected to install CPU-only PyTorch from the
official CPU wheel index before Memory requirements. The regression was then
captured in `tests/tools/test_memory_deployment.py`: the new test failed against
pre-fix commit `26901ce`, passed after the CPU-only fix, and the complete suite
finished with 594 passed tests and one known non-blocking Starlette/httpx
TestClient deprecation warning. The fix is commit `26c0da0`, the regression test
is commit `ddb73ec`, and both CT105 and CT108 were aligned to `ddb73ec`.

Router/Admin CT108 is configured with
`NYRA_MEMORY_URL=http://192.168.0.13:8090` and
`NYRA_MEMORY_TIMEOUT_SECONDS=3.0`. Production verification confirmed Router
`HEALTHY`/`READY`, Memory `healthy`/`ready`, and HTTP 200 for both Nyra Admin
Memory pages. Operational Memory create/read/delete was exercised end to end
through Router and cleaned up afterward. Semantic Memory
create/read/search/confirm/delete was also exercised through Router, returned
the production multilingual embedding model and a similarity result, and was
cleaned up afterward. CT108's `.env`, runtime `data/`, and `backups/` were
preserved during repository alignment.

### Milestone 5 production verification

M5 production deployment and physical verification completed on 2026-09-10.
The deployed Router repository revision is
`348d2d8738132713479d32c1a94f84b2d458a13d`. The dedicated Skills service uses
`/opt/nyra-skills` for replaceable application code,
`/var/lib/nyra-skills/jobs.sqlite3` for persistent job state, and
`/etc/nyra/skills.env` for operator-managed configuration. The legacy
`/opt/nyra-skills/.env` was removed after successful deployment gates, and the
active Skills configuration contains no direct Home Assistant URL/token.

The final local regression before deployment completed with 738 passed tests
and two known non-blocking dependency deprecation warnings. During deployment,
two production-discovered defects were fixed with permanent regression
coverage: duplicate builtin Skill priorities preventing readiness, and the
deployment verifier missing the production `PYTHONPATH`. The corrected
repository verifier then passed against the deployed service.

Physical verification exercised the real production boundaries. An exact
Home Assistant resolve returned
`light.mansarda_scrivania_bianca_lampada`; the authorized light was changed from
on to off through Skills -> Router Home Assistant capability -> Home Assistant
and restored to its original on state. The same distributed trace contained
Skills execution plus Router `ha.resolve` and `ha.execute` spans with
parent-child correlation. An ambiguous `lampada` reference returned two
candidates and `NEEDS_CLARIFICATION` without executing either target.

A disposable Nyra-managed Behavior was created, read back with the `NYRA`
ownership marker, and deleted; a subsequent read returned `NOT_FOUND`. An
explicit semantic Memory marker was created through Router -> Skills -> Router
Memory management and then deleted. A far-future disposable job remained
`SCHEDULED` across a controlled `nyra-skills.service` restart, was visible
through Router-backed Admin diagnostics, and was then cancelled. SQLite
integrity remained `ok`, Skills and Router returned ready after restart, and
the Skills systemd service remained enabled/active.

Pre-M5 rollback archives remain checksum-valid and readable:
`/var/backups/nyra-skills/pre-m5-20260910T132332Z.tar.gz` and
`/var/backups/nyra-router/pre-m5-20260910T134732Z.tar.gz`. Verification was
non-destructive because production remained healthy; no restore was performed.
The Home Assistant adapter backup created for the coordinated deployment also
remains the rollback reference for the M5 Home Assistant capability change.

The Speaker-ID container is a fresh Debian 12 deployment built by
`deploy/bootstrap/speaker-id.sh`. It runs as the unprivileged
`nyra-speaker-id` user, persists data and the ECAPA model cache under
`/var/lib/nyra-speaker-id`, and reports ready only after a real model inference
succeeds. Router streams audio to
`ws://192.168.0.14:8090/v1/audio/stream`.

Deployment verification completed on 2026-09-07: Router, Nyra Admin,
Speaker-ID, and Home Assistant report healthy/ready; Nicola's profile contains
six accepted Mansarda samples and a physical Assist request produced
`IDENTIFIED` before the deployment. Nyra Admin exposes profile audio and
metadata, recent identity diagnostics with retention-aware detail, and
wake-word sample listening/deletion/export through Router APIs only.

Nyra Mansarda runs the ESPHome 2026.8.2 enrollment/wake-capture firmware built
on 2026-09-08. The OTA image SHA-256 is
`9ef1e2e40945b1ff4e7c69199fe53231c1941f346f62724d4dd31fda943b6c25`
(ESPHome build hash `0x3017e61c`). OTA completed successfully only on
`192.168.0.141`; the device passed the 60-second boot-loop guard and restored
its encrypted ESPHome API connection. This build acknowledges wake-word
detection with the white listening visual immediately, while Assist audio
starts as soon as the local wake-cue announcement actually finishes instead of
waiting for a fixed one-second delay. The wake cue remains outside STT and
Speaker-ID audio.

The trusted user display-name change was deployed to Router/Admin and Home
Assistant on 2026-09-08. Home Assistant remains authoritative for the current
name, Router persists the mapping from the stable Home Assistant user ID, and
Nyra Admin presents the name while retaining the ID as secondary diagnostic
data. Existing Speaker-ID profiles are enriched dynamically and their
biometric records remain ID-only. Router returned `HEALTHY` and `READY`, Admin
returned HTTP 200, `ha core check` succeeded, and Home Assistant restarted
normally. Opening Configurazione Nyra synchronized `Nicola Residori`; the name
was then verified in the profile, identity diagnostic, diagnostic candidate,
and Wake Word sample views.

On 2026-09-08 the live Speaker-ID threshold was calibrated from `0.40` to
`0.38`, with the margin unchanged at `0.07` (configuration revision `2`).
Nicola then refreshed the Mansarda profile from 12 to 18 accepted samples. The
first physical request after that refresh was `IDENTIFIED` as `Nicola Residori`
with score `0.46259344812746`. Earlier very short requests remained variable,
so repeated short-command validation is still required before treating the
calibration as final.

Task 19 regression verification completed on 2026-09-08. The simulated M3
suite covers identified, Guest, continuity and changed-user resolution, short
requests, Speaker-ID failure, timeout/late-result behavior, runtime timeout
snapshots, enrollment terminal behavior, every Wake Word result, and
interleaved streams. Home Assistant fallback responses are localized for
`it-IT` and `en-US` and do not hardcode the assistant's spoken name. A
Speaker-ID connection failure now yields the typed
`FAILED/SERVICE_UNAVAILABLE` identity result and the Router continues with
session continuity or Guest instead of aborting the request.

Fresh-CT and reboot verification completed on CT106 on 2026-09-08 using
`deploy/verify/speaker-id.sh`. Before and after the reboot, the service user,
application/data layout, Python dependencies, both SQLite databases, systemd
enablement/activity, ECAPA inference, model cache, `/health`, and `/ready`
passed. The saved persistence manifest confirmed unchanged threshold, margin,
configuration revision, schema, profile/enrollment counts, and Wake Word
counts. A generated PCM stream sent through the production Router returned a
typed `NOT_RECOGNIZED/BELOW_THRESHOLD` result from CT106 while preserving its
request, session, source, trace, and Router audio-relay span correlation.

The Task 18–19 Router changes and localized Home Assistant fallback were
deployed on 2026-09-08. After successful Router and Home Assistant restarts,
Router reported `HEALTHY`/`READY`, Home Assistant returned HTTP 200, and the
production Router-to-Speaker-ID relay test passed again. The Wake Word export
path produced a valid `.tar.gz` containing selected WAV audio and
`metadata.json`. CT106 and CT108 contain no `nyra-voice` service or runtime
reference; the former CT106 was already replaced by the fresh dedicated
Speaker-ID container.

The first post-deployment physical Mansarda request completed normally. The
initial “Chi sono?” validation exposed a stale speaker session: the biometric
attempt scored `0.366723`, correctly produced two red blinks, but the response
used continuity from an earlier wake word. Home Assistant now closes a speaker
session after every terminal response or Router failure, while preserving it
only for an immediate clarification. Each new wake word therefore creates a
new `session_id`. The localized Router identity-query skill answers with the
trusted display name only when the current session resolves that identity and
never speaks a technical ID or `guest`.

Physical verification after the fix produced “Sei Nicola Residori.” The two
latest wake-word activations had distinct session IDs and both produced
`IDENTIFIED`, scoring `0.526898` and `0.417643`. After eight physical production
attempts, identity metrics reported 75% `IDENTIFIED`, 25% `NOT_RECOGNIZED`, no
failures/timeouts/late results, p50 `776 ms`, p95 `2618 ms`, and p99 `2631 ms`.
The Router timeout remains `6.0 s` (revision `2`), which retains a substantial
safety margin above the observed p95.

Local verification reports 476 passed tests, successful Python bytecode
compilation, valid deployment shell syntax, no whitespace errors, and no
display-name fields in Speaker-ID or general observability storage.

Router and Admin remain separate applications. Installation-specific Home Assistant and ESPHome values are intentionally not committed as project defaults.

## Migration status

Home Assistant, the Speaker-ID/voice-identity domain, Memory, and Skills are
migrated to the Nyra v1 Router lifecycle through Milestone 5. The Router owns
the Home Assistant capability boundary used by Skills. LLM specialist
integration remains scheduled for Milestone 6; no LLM-proposed side effect may
bypass the Skills validation/action gate.

## Known follow-up work

These items do not block the completed Milestone 3:

- perform an additional unknown-speaker physical identity check when another
  speaker is available
- migrate LLM access in Milestone 6 through the existing Router -> Skills action gate
- eliminate remaining deployment-only compatibility/manual packaging steps during productization
- extend multi-speaker physical validation as additional speakers are provisioned
- improve audio-reactive visuals if a reliable PCM amplitude hook becomes available

## Next step

Start Milestone 6 — LLM — from the deployed M5 trust boundary: Router-managed
reasoning, provider-independent configuration, context propagation, and
LLM-proposed actions validated/materialized by Skills before any Router-owned
capability executes.
