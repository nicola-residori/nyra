# Nyra Current State

## Version

Nyra v1.0-dev

## Current milestone

Milestone 2 — Home Assistant adapter and Nyra speaker integration — is complete.

The next milestone is Milestone 3 — Identity and Voice.

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
- custom local Italian `Nyra` micro-wake-word model with stock base wake words retained
- physical path validated: wake word -> ESPHome -> Home Assistant -> Router -> Home Assistant -> TTS/speaker

## Deployment

- `nyra-router`: port `8090`
- `nyra-admin`: port `80`

Router and Admin remain separate applications. Installation-specific Home Assistant and ESPHome values are intentionally not committed as project defaults.

## Migration status

Home Assistant is migrated to the Nyra v1 Router lifecycle for Milestone 2. Production Skills, Memory, Voice, and LLM specialist integrations are not yet migrated. Existing implementations may remain operational as functional references until their Nyra v1 replacements are validated.

## Known follow-up work

These items do not block Milestone 2:

- migrate Voice and identity processing in Milestone 3
- migrate Memory in Milestone 4
- migrate Skills and Router-owned Home Assistant capabilities in Milestone 5
- migrate LLM access in Milestone 6
- eliminate remaining deployment-only compatibility/manual packaging steps during productization
- extend multi-speaker physical validation as additional speakers are provisioned
- improve audio-reactive visuals if a reliable PCM amplitude hook becomes available

## Next step

Begin Milestone 3 — Identity and Voice — from the completed Home Assistant/speaker boundary.
