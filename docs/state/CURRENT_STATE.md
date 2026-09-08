# Nyra Current State

## Version

Nyra v1.0-dev

## Current milestone

Milestone 2 — Home Assistant adapter and Nyra speaker integration — is complete.

Milestone 3 — Identity and Voice — is in progress. Speaker-ID, physical
enrollment, identity validation, wake-word sample capture, and the identity
management views in Nyra Admin and trusted Home Assistant user-name enrichment
are deployed. Broader M3 observability and regression tasks remain.

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

- `nyra-router`: CT `108`, `192.168.0.16`, port `8090`
- `nyra-admin`: CT `108`, `192.168.0.16`, port `80`
- `nyra-speaker-id`: CT `106`, `192.168.0.14`, port `8090`

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
and Wake Word sample views. The new physical identification smoke test remains
pending.

Local verification reports 448 passed tests, successful Python bytecode
compilation, no whitespace errors, and no display-name fields in Speaker-ID or
general observability storage.

Router and Admin remain separate applications. Installation-specific Home Assistant and ESPHome values are intentionally not committed as project defaults.

## Migration status

Home Assistant is migrated to the Nyra v1 Router lifecycle for Milestone 2. Production Skills, Memory, Voice, and LLM specialist integrations are not yet migrated. Existing implementations may remain operational as functional references until their Nyra v1 replacements are validated.

## Known follow-up work

These items do not block Milestone 2:

- perform an additional unknown-speaker physical identity check
- physically validate trusted Home Assistant user-name enrichment
- complete the remaining Milestone 3 observability, settings, and E2E work
- migrate Memory in Milestone 4
- migrate Skills and Router-owned Home Assistant capabilities in Milestone 5
- migrate LLM access in Milestone 6
- eliminate remaining deployment-only compatibility/manual packaging steps during productization
- extend multi-speaker physical validation as additional speakers are provisioned
- improve audio-reactive visuals if a reliable PCM amplitude hook becomes available

## Next step

Run one natural physical request from Nyra Mansarda and confirm that the first
command words are captured immediately after the wake cue, then verify that its
identity diagnostic resolves the stable Home Assistant ID to `Nicola Residori`.
