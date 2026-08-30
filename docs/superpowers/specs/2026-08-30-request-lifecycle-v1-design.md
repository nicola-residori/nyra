# N.Y.R.A. Request Lifecycle v1 Design

## Goal
Define the canonical synchronous user-request lifecycle for Router: ingress metadata, UUID ownership, clarification traces, jobs, identity, interaction states, WebSocket delivery, and observability.

## Ingress
Trusted user clients call `POST /v1/requests` synchronously. The call ends with `completed`, `needs_clarification`, or failure.

Ingress provides only raw user input plus minimum trusted metadata:
- `type`
- `session_id`
- `request_id`
- `language`
- optional `source`
- optional trusted `identity`
- `input.text`

Initial types: `ha_speaker`, `ha_assist`, `job`, `nyra_ui`.

HA must not send Memory context, entity dumps, policies, routing decisions, skill choices, or LLM instructions.

## Identifier semantics
`session_id`, `request_id`, and `trace_id` are UUIDs. `span_id` remains `CT#operation#random`.

- `session_id`: created by the trusted user ingress and propagated unchanged.
- `request_id`: created by the trusted ingress for a new functional user request.
- Clarification follow-ups keep the same session/request UUIDs.
- `trace_id`: created by Router for each technical execution/turn. A clarification follow-up gets a new trace UUID.
- One operation keeps the same span ID from REQUEST through intermediate logs to RESPONSE or FAULT.

Hierarchy: `SESSION -> REQUEST -> one or more TRACES -> SPANS`.

## Jobs
Background jobs have no active session or request:
- `session_id = null`
- `request_id = null`
- `trace_id = UUID`
- `origin_request_id = UUID | null`

`origin_request_id` links a delayed job to the user request that created it. Pure internal jobs leave it null.

## Source
`source` identifies a meaningful physical/contextual origin, never user identity.

For `ha_speaker`, HA supplies speaker `id` and resolved `area`. For `ha_assist`, `job`, or clients without a meaningful physical origin, `source` may be null.

## Language
`language` is trusted ingress metadata, e.g. the language configured for the HA Assist pipeline. Router uses it as the interaction and default response language.

## Identity
User IDs are canonical and identical across Nyra and Home Assistant; there is no mapping layer.

For `ha_assist`, HA supplies the authenticated identity. For `ha_speaker`, HA supplies no identity: Router sees the type and invokes Speaker ID itself, in parallel with identity-independent processing.

Identity outcome events:
- `IDENTITY_IDENTIFIED`
- `IDENTITY_CONFIRMED`
- `IDENTITY_CHANGED`
- `IDENTITY_GUEST`

These are events, not interaction states. Failed recognition resolves to canonical `guest`.

## Request persistence and clarification
Router owns request state; HA does not carry Nyra semantic context.

Persist separately from observability logs:
- request/session UUIDs
- type/language/source/current identity
- original input
- status/current trace UUID
- timestamps
- pending state needed to resume clarification

V1 uses Router SQLite.

A `needs_clarification` response returns the same session/request IDs and the current trace ID. The follow-up POST keeps session/request IDs; Router creates a new trace and resumes persisted pending state.

Clarification expiration is configurable; v1 default is 120 seconds. Expired pending requests become `expired`.

## HTTP response
Completed example:

```json
{
  "status": "completed",
  "session_id": "UUID",
  "request_id": "UUID",
  "trace_id": "UUID",
  "response": {"text": "Fatto."}
}
```

Clarification uses `status = needs_clarification` and a user-facing question.

## Real-time event channel
Command channel: `POST /v1/requests`, one synchronous call per interaction turn/trace.

Event channel: `WS /v1/events`, client-initiated and persistent. HA opens it at integration startup and keeps it open. ESPHome speakers do not connect directly to Router.

Clients authenticate and subscribe to event categories.

## WebSocket resilience
Clients must reconnect after HA or Router restart, re-authenticate, re-subscribe, and resynchronize current interaction state.

Use heartbeat/ping-pong and bounded exponential reconnect backoff:
`1s -> 2s -> 5s -> 10s -> 30s -> 30s ...`

Successful connection resets backoff. V1 does not replay every missed event; reconnect performs current-state resynchronization.

## Interaction states
Ingress/HA owns physical audio states:
- `IDLE`
- `LISTENING`
- `SPEAKING`

Router owns:
- `PROCESSING`
- `IDENTIFYING`
- `MEMORY`
- `SKILL_CHECK`
- `SKILL_EXECUTION`
- `LLM_REASONING`
- `NEEDS_CLARIFICATION`
- `ERROR`

States are user-visible logical feedback, not a serialization of all internal work. Internal operations may run concurrently.

Router publishes logical states, not LED commands. HA maps states to speaker effects; e.g. `LLM_REASONING` may render as rainbow. Future Nyra UI clients can render the same states differently.

## Memory and skills
Router owns contextual enrichment.

Operational Context Resolution is deterministic and always performed when applicable. Semantic long-term Memory search is conditional. Both may render as `MEMORY`, while observability distinguishes `CONTEXT_RESOLUTION` and `MEMORY_SEARCH`.

`SKILL_CHECK` is distinct from `SKILL_EXECUTION`; a miss may transition to `LLM_REASONING`.

## Observability
Every technical operation follows:
`REQUEST -> zero or more EVENT/DEBUG/WARN -> RESPONSE or FAULT`, with the same span ID.

Lifecycle, identity outcomes, state changes, Memory operations, Skill checks, and WebSocket lifecycle use stable English technical event names.

Repository code, comments, docs, API names, technical log events, and test data are English. Raw user input and user-facing responses may use the interaction language.

## Trust
Only authenticated trusted ingress clients may submit ingress-owned identifiers and trusted identity.

Router validates UUID syntax, type, type-specific required fields, caller authorization for the claimed type, and identity provenance. Downstream services cannot override trusted session/request/source/identity fields.

## V1 implementation scope
This milestone provides:
- request protocol models and validation
- synchronous `/v1/requests`
- Router-created trace UUIDs
- persistent request/clarification state
- job-compatible execution context
- interaction-state model
- WebSocket events/subscriptions
- reconnect/resync contract support
- lifecycle observability
- tests for UUID ownership, clarification trace reuse, jobs, identity outcomes, and WebSocket state behavior

Migration of Skills, Memory, Voice, and the production HA adapter follows later.
