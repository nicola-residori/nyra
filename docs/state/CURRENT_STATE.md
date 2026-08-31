# Nyra Current State

## Version

Nyra v1.0-dev

## Current milestone

Shared Protocol + Router Component Contract v1 foundation implemented in the working package.

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
- shared Component Contract v1 protocol primitives for correlation, service status, RequestContext, semantics, execution, behaviors, and capabilities
- Router `/health` and `/ready` standardized on shared service status contracts
- central observability reconstructs authoritative session correlation from `request_id` / `origin_request_id`

## Deployment

- `nyra-router`: port `8090`
- `nyra-admin`: port `80`

Router and Admin remain separate applications.

## Migration status

Production Skills, Memory, Voice, and Home Assistant are not yet migrated to the v1 Router lifecycle. Existing alpha services remain operational until their replacements are validated.

## Next step

Validate and deploy the Shared Protocol + Router foundation before beginning one-at-a-time specialist component migrations.
