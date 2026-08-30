# N.Y.R.A. Request Lifecycle v1 Design

## Goal
Define the canonical synchronous user-request lifecycle for Router: ingress metadata, prefixed UUID ownership, clarification traces, forced conversational closure, jobs, identity, interaction states, WebSocket delivery, and observability.

## Ingress
Trusted user clients call `POST /v1/requests` synchronously. The call ends with `completed`, `needs_clarification`, `closed`, or failure.

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
`session_id`, `request_id`, and `trace_id` use semantic prefixes plus UUIDs: `ses_<UUID>`, `req_<UUID>`, and `trc_<UUID>`. `span_id` remains `CT#operation#random`.

- `session_id`: created by the trusted user ingress and propagated unchanged.
- `request_id`: created by the trusted ingress for a new functional user request.
- Clarification follow-ups keep the same session/request UUIDs.
- `trace_id`: created by Router for each technical execution/turn as `trc_<UUID>`. A clarification follow-up gets a new trace ID.
- One operation keeps the same span ID from REQUEST through intermediate logs to RESPONSE or FAULT.

Hierarchy: `SESSION -> REQUEST -> one or more TRACES -> SPANS`.

## Jobs
Background jobs have no active session or request:
- `session_id = null`
- `request_id = null`
- `trace_id = trc_<UUID>`
- `origin_request_id = req_<UUID> | null`

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

## Request terminal statuses
The canonical request statuses are:
- `completed`
- `needs_clarification`
- `closed`
- `failed`
- `expired`

`completed` means the functional request completed normally. The ingress may apply its normal conversational/follow-up behavior.

`needs_clarification` means the functional request remains open and Router expects continuation using the same `session_id` and `request_id`.

`closed` is an authoritative Router instruction to terminate the conversational session after any response has been rendered. The ingress MUST NOT open or resume follow-up after receiving `closed`.

`failed` represents a failed execution.

`expired` represents a previously pending request that can no longer be resumed.

### Closed response

```json
{
  "status": "closed",
  "session_id": "ses_<UUID>",
  "request_id": "req_<UUID>",
  "trace_id": "trc_<UUID>",
  "response": {
    "text": "Fatto."
  },
  "close_reason": "direct_command"
}
```

`response` may be null when no spoken/displayed acknowledgement is required.

Stable initial close reasons:
- `explicit_close`
- `direct_command`
- `alarm_dismissed`
- `timeout`
- `policy`

Close reasons explain why closure occurred; they do not change the protocol behavior of `closed`.

## Forced closure and alarms
Forced closure is part of the Router protocol rather than a Home Assistant workaround.

A direct command may return `closed` when its semantics require completion without conversational follow-up.

For an active alarm, the alarm execution itself may be a background job with no active session/request IDs and an optional `origin_request_id`. If the user invokes Nyra to dismiss the alarm, that new user interaction receives its own session/request/trace identifiers. Router handles the alarm dismissal and returns `closed`, optionally with `response = null`.

The ingress then:
1. stops/renders the requested action;
2. does not enter follow-up listening;
3. returns the speaker/client to `IDLE`.

This prevents an alarm-dismiss wake word from accidentally opening a new conversational follow-up.

## Session closure event
Router emits a stable technical event when it authoritatively closes a conversational session:

`SESSION_CLOSED`

The event is correlated with available session/request/trace/source identifiers and carries the stable close reason.

This event is observable and may also be delivered through the real-time event channel where useful. The HTTP `status = closed` remains the authoritative command-channel result for the active request.

## HTTP response
Completed example:

```json
{
  "status": "completed",
  "session_id": "ses_<UUID>",
  "request_id": "req_<UUID>",
  "trace_id": "trc_<UUID>",
  "response": {"text": "Fatto."}
}
```

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

Lifecycle, identity outcomes, `SESSION_CLOSED`, state changes, Memory operations, Skill checks, and WebSocket lifecycle use stable English technical event names.

Repository code, comments, docs, API names, technical log events, and test data are English. Raw user input and user-facing responses may use the interaction language.

## Trust
Only authenticated trusted ingress clients may submit ingress-owned identifiers and trusted identity.

Router validates prefixed UUID syntax, type, type-specific required fields, caller authorization for the claimed type, and identity provenance. Downstream services cannot override trusted session/request/source/identity fields.

## V1 implementation scope
This milestone provides:
- request protocol models and validation
- synchronous `/v1/requests`
- Router-created trace UUIDs
- persistent request/clarification state
- authoritative `closed` response semantics and `SESSION_CLOSED`
- job-compatible execution context
- interaction-state model
- WebSocket events/subscriptions
- reconnect/resync contract support
- lifecycle observability
- tests for prefixed UUID ownership, clarification trace reuse, forced closure/no-follow-up semantics, jobs, identity outcomes, and WebSocket state behavior

Migration of Skills, Memory, Voice, and the production HA adapter follows later.


## Correlation ID Format

Canonical correlation identifiers are human-readable prefixed UUIDs:

```text
session_id = ses_<UUID>
request_id = req_<UUID>
trace_id   = trc_<UUID>
span_id    = CT#operation#random
```

The prefixes are part of the canonical identifier and MUST be preserved end-to-end. Job executions keep `session_id` and `request_id` null while always carrying a `trc_<UUID>` trace ID. Historical observability rows are preserved during schema migration, but newly ingested v1 records must use canonical prefixed IDs.
