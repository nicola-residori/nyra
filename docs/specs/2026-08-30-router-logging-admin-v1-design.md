# Nyra Router, Logging, Tracing, and Admin v1 Design

**Status:** Proposed  
**Date:** 2026-08-30

## 1. Scope

This design defines the first production milestone of Nyra v1:

- Nyra Router foundation
- centralized structured logging
- distributed tracing
- centralized log storage
- Nyra Admin
- request, trace, span, and session observability
- structured JSON request/response/fault visualization
- service health visibility

This milestone does not yet migrate Skills, Memory, Voice, LLM, or the Home
Assistant adapter to Nyra v1. The existing alpha system remains operational
until each component is migrated.

## 2. Components

### 2.1 Nyra Router

Nyra Router is the trusted orchestration and observability backend.

Initial responsibilities in this milestone:

- expose a health endpoint
- generate and propagate distributed identifiers
- ingest structured log records
- persist logs and trace metadata
- expose query APIs for Nyra Admin
- expose service health APIs
- provide the backend foundation for future request orchestration

Nyra Router listens on port `8090`.

Nyra Router does not contain the Nyra Admin UI implementation.

### 2.2 Nyra Admin

Nyra Admin is a separate application and codebase inside the same monorepo.

Nyra Admin:

- listens on port `80`
- exposes the only human-facing Nyra administration interface
- communicates with Nyra Router exclusively through Router APIs
- does not access Router SQLite databases directly
- does not contain Router orchestration logic

The initial implementation uses FastAPI plus server-rendered HTML, CSS, and
vanilla JavaScript.

The frontend is intentionally decoupled from Router APIs so that it can later be
replaced by another frontend technology without changing Router internals.

## 3. Repository Structure

```text
nyra/
├── router/
│   ├── app.py
│   ├── api/
│   ├── core/
│   ├── logging/
│   ├── tracing/
│   ├── storage/
│   └── config/
│
├── admin/
│   ├── app.py
│   ├── routes/
│   ├── templates/
│   └── static/
│       ├── css/
│       └── js/
│
├── shared/
│   ├── protocol/
│   ├── logging/
│   └── models/
│
└── deploy/
    ├── bootstrap/
    ├── proxmox/
    └── systemd/
```

Router and Admin are deployed independently even when they initially run in the
same Proxmox container.

## 4. Network and Ports

Initial deployment:

```text
Nyra Router  :8090
Nyra Admin   :80
```

No deployment-specific IP address is hardcoded in source code.

Nyra Admin obtains the Router address from configuration.

## 5. Distributed Identifiers

Nyra uses four primary observability identifiers.

### 5.1 sessionId

Identifies a complete conversational session.

Example:

```text
ses_01K...
```

### 5.2 requestId

Identifies a single functional request or conversational turn.

Example:

```text
req_01K...
```

### 5.3 traceId

Identifies one distributed technical execution.

A functional request may result in multiple traces in cases such as retries or
asynchronous execution.

Example:

```text
trc_01K...
```

### 5.4 spanId

Identifies a single technical operation.

Required format:

```text
CT#operation#random
```

Examples:

```text
ROUTER#request_ingress#8F3A12
VOICE#speaker_identification#19BC77
MEMORY#context_resolve#02AA91
SKILLS#execute#73F0C1
ROUTER#home_assistant_call#A8DD44
```

The random suffix is generated locally by the component creating the span and
must be sufficiently collision-resistant for the expected workload.

### 5.5 parentSpanId

Identifies the parent span when the current operation was caused by another
operation.

### 5.6 originRequestId

Identifies the original request that caused a later asynchronous operation.

Example: a reminder created at 20:00 and executed at 21:00.

## 6. Identifier Ownership

Router creates:

- sessionId
- requestId
- traceId

Downstream components propagate these identifiers unchanged.

A component may create a new spanId when it begins a new operation.

A downstream component must not invent a new sessionId or requestId for a child
operation.

A new traceId may be created only for a semantically new technical execution,
such as a retry or later asynchronous execution.

## 7. Log Record Model

Every persisted log record contains structured fields.

Required fields:

```text
timestamp=
CT=
level=
kind=
event=
sessionId=
requestId=
traceId=
spanId=
```

Context-dependent fields:

```text
parentSpanId=
originRequestId=
operation=
result=
errorCode=
httpStatus=
retryCount=
source=
identity=
area=
sessionElapsedMs=
requestElapsedMs=
traceElapsedMs=
spanElapsedMs=
```

Additional parameters use:

```text
name=value
```

Parameters are stored as structured key/value data rather than preformatted log
strings.

## 8. Log Kinds

Every log record has one kind:

- `REQUEST`
- `RESPONSE`
- `FAULT`
- `EVENT`

Nyra Admin must make the kind visually obvious without requiring the user to
read the event name.

## 9. Log Levels

Nyra uses:

- `TRACE`
- `DEBUG`
- `INFO`
- `WARN`
- `ERROR`
- `CRITICAL`

The log level is mandatory, indexed, searchable, and filterable.

Suggested semantics:

- TRACE: very fine-grained diagnostic detail
- DEBUG: technical diagnostic information
- INFO: normal significant operations
- WARN: recoverable abnormal conditions
- ERROR: failed operations
- CRITICAL: service-threatening or system-threatening failure

## 10. Events

Events use stable machine-readable codes.

Examples:

```text
REQUEST_RECEIVED
REQUEST_COMPLETED
REQUEST_FAILED
IDENTITY_START
IDENTITY_RESOLVED
CONTEXT_RESOLUTION_START
CONTEXT_RESOLUTION_COMPLETED
MEMORY_LOOKUP
MEMORY_RESULT
SKILL_MATCH
SKILL_MISS
LLM_REQUEST
LLM_RESPONSE
CAPABILITY_REQUEST
POLICY_CHECK
HOME_ASSISTANT_REQUEST
HOME_ASSISTANT_RESPONSE
SERVICE_HEALTH_CHANGED
```

Human-readable messages are optional and never replace the event code.

## 11. JSON Payloads

Request, response, and fault payloads remain structured JSON.

The storage layer stores payloads as JSON-compatible structured data.

Nyra Admin:

- never renders JSON payloads as a single unformatted line
- shows a compact preview in the log table when appropriate
- shows the complete payload in an expanded view
- pretty-prints payloads with indentation
- clearly labels request, response, and fault payloads

## 12. Timing Model

Nyra tracks elapsed time in milliseconds for all four logical levels:

```text
sessionElapsedMs=
requestElapsedMs=
traceElapsedMs=
spanElapsedMs=
```

Definitions:

- `sessionElapsedMs`: elapsed time since the session began
- `requestElapsedMs`: duration of the functional request
- `traceElapsedMs`: duration of the technical execution
- `spanElapsedMs`: duration of the individual operation

Start records may omit a final elapsed value because the operation has not yet
completed.

Completion, response, or fault records include the final elapsed value when it
is known.

Nyra Admin may calculate live elapsed values for currently active objects.

## 13. Logging API

Router exposes a versioned ingestion endpoint:

```text
POST /v1/logs/ingest
```

The endpoint accepts batches of structured log records.

The initial design supports single-record ingestion only as a compatibility
case. Production service logging should use batches.

Router validates:

- required fields
- identifier format
- level
- kind
- event presence
- payload type
- supported schema version

Malformed records are rejected explicitly.

## 14. Logging Client Behavior

Nyra services use a shared logging client.

Application code emits semantic logging calls rather than manually building
transport payloads.

Example concept:

```python
logger.info(
    event="SKILL_MATCH",
    kind="EVENT",
    skill="action",
    confidence=1.0,
)
```

The shared logger automatically adds the active:

- sessionId
- requestId
- traceId
- spanId
- parentSpanId
- service/CT identifier
- timestamp

Logging must not block the request path.

The shared client therefore uses:

```text
application
    |
    v
non-blocking local queue
    |
    v
background batch worker
    |
    v
Router /v1/logs/ingest
```

If Router is unavailable, the client uses a bounded local spool and retries.

Logging failure must never cause the functional operation to fail.

## 15. Secret Redaction

Redaction occurs before persistence and before a log record leaves the service
that generated it.

At minimum, these parameter names are treated as sensitive:

- authorization
- token
- api_key
- password
- secret
- cookie

Matching is case-insensitive.

Sensitive values are replaced with:

```text
***REDACTED***
```

The redaction design must support additional configured keys later.

## 16. Storage

The first implementation uses SQLite in WAL mode.

The storage design is accessed only through Router storage abstractions.

Nyra Admin never opens the database directly.

Logs are indexed at least by:

- timestamp
- CT
- level
- kind
- event
- sessionId
- requestId
- traceId
- spanId

Additional indexes may be introduced based on measured query patterns.

The design must allow a future migration to Loki, PostgreSQL, OpenTelemetry, or
another telemetry backend without changing service logging APIs.

## 17. Nyra Admin v1

Nyra Admin is the single Nyra administration UI.

Initial pages:

```text
Dashboard
Logs
Requests
Sessions
Traces
Services
```

Future service-specific pages may include:

```text
Skills
Memory
Voice
LLM
Home Assistant
Automations
Configuration
```

These pages obtain data by calling Router or Router-mediated service APIs.

## 18. Logs Page

The Logs page is the first complete Admin feature.

The table clearly presents:

- timestamp
- CT
- level
- kind
- sessionId
- requestId
- traceId
- spanId
- event
- elapsed timing
- result

Each CT has a stable visual identity in the UI.

Each log kind is visually distinct.

Log levels are also visually clear.

The exact color palette is a UI implementation detail and is not part of the
protocol contract.

## 19. Log Search and Filters

The Logs page supports:

- free-text search
- CT filter
- level filter
- kind filter
- event filter
- result filter
- sessionId filter
- requestId filter
- traceId filter
- spanId filter
- time range filter
- live mode

Free-text search may match structured parameters and JSON payload content.

Identifiers displayed in the UI are clickable.

Selecting one applies the relevant filter or navigates to the corresponding
object view.

## 20. Requests Page

A request row shows at least:

- request timestamp
- requestId
- sessionId
- source
- identity when available
- original request text when available
- result
- total elapsed milliseconds

Opening a request displays:

- request metadata
- all related traces
- all related spans
- related logs
- request and response payloads
- timing breakdown

## 21. Sessions Page

A session row shows at least:

- sessionId
- start time
- end time or active status
- source
- identity when available
- request count
- total elapsed milliseconds

Opening a session displays all requests in chronological order.

## 22. Traces Page

A trace row shows at least:

- traceId
- requestId
- start time
- result
- total elapsed milliseconds
- span count

Opening a trace provides both:

- a chronological log view
- a timing-oriented span tree/timeline

The trace view should make bottlenecks visible at a glance.

## 23. Span View

A span view displays:

- spanId
- parentSpanId
- CT
- operation
- start time
- end time
- spanElapsedMs
- result
- related request/response/fault/event logs
- structured payloads

## 24. Services Page

The initial Services page shows at least:

- Router
- Admin
- configured first-level services
- Home Assistant when configured

For each service:

- configured endpoint
- health
- last successful check
- last error when applicable
- response latency when measurable

Service credentials are never displayed.

## 25. Router Health Endpoint

Router exposes:

```text
GET /health
```

The endpoint returns structured JSON containing at least:

- service name
- version
- status
- uptime
- timestamp

The health endpoint must remain lightweight and must not perform expensive
downstream checks.

## 26. Admin Health Endpoint

Nyra Admin exposes its own lightweight health endpoint.

Admin health is independent of Router health.

The Admin UI should clearly indicate when Admin itself is available but Router
is unavailable.

## 27. Error Handling

### Router storage failure

Router returns a clear server error for ingestion or query operations that
cannot be completed.

Functional Nyra request processing must eventually be designed so logging
storage failure does not stop user operations.

### Admin cannot reach Router

Admin remains available and presents a clear Router-unavailable state.

### Invalid log record

The ingest API rejects invalid records with structured validation details.

### Partial log batch failure

The batch API reports rejected records explicitly and must not silently discard
malformed records.

## 28. Configuration

Configuration precedence:

```text
environment variables
        >
configuration file
        >
safe defaults
```

Router and Admin have separate configuration objects.

No source code contains deployment-specific addresses or credentials.

Admin configuration includes the Router API URL.

## 29. Deployment

Initial deployment uses the existing `nyra-router` Debian 12 Proxmox container.

Both applications may initially run in this container:

```text
nyra-router -> port 8090
nyra-admin  -> port 80
```

They run as separate systemd services.

They have separate processes, startup behavior, logs, configuration, and
application entry points.

This co-location is a deployment decision only. The software architecture does
not depend on it.

## 30. Testing

The first milestone requires automated tests for at least:

- identifier generation
- spanId format
- log validation
- log level validation
- log kind validation
- secret redaction
- SQLite persistence
- indexed query behavior
- ingestion endpoint
- filtering by core identifiers
- JSON payload preservation
- Router health endpoint
- Admin-to-Router API behavior

UI smoke tests verify that:

- Logs page loads
- filters can be applied
- request/response/fault kinds are distinguishable
- JSON expands and is formatted
- IDs are clickable
- Router-unavailable state is handled

## 31. Initial Success Criteria

Milestone 1 is complete when:

1. Router runs on port 8090 as its own service.
2. Admin runs on port 80 as its own service.
3. Router persists structured logs in SQLite WAL mode.
4. Logs can be ingested through the versioned API.
5. Nyra Admin displays logs from Router.
6. Request, response, fault, and event records are visually distinct.
7. JSON payloads are pretty-printed.
8. CT, level, kind, sessionId, requestId, traceId, spanId, and event are
   searchable and filterable.
9. session/request/trace/span elapsed milliseconds are visible.
10. IDs are clickable and navigable.
11. Router and Admin health are visible.
12. No deployment-specific IPs or credentials are hardcoded.
13. Automated tests pass.
14. The repository contains the deployment and architecture documentation needed
    to reproduce the milestone.
