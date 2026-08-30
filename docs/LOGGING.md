# Nyra Logging and Tracing Protocol

**Status:** Draft v1

Nyra uses centralized structured logging and distributed tracing.

## Core identifiers

- `sessionId`: complete conversational session.
- `requestId`: single functional request or conversational turn.
- `traceId`: distributed technical execution of a request.
- `spanId`: single technical operation inside a trace.
- `parentSpanId`: span that caused the current span.
- `originRequestId`: original request for asynchronous operations.

`spanId` format:

```text
CT#operation#random
```

## Required log fields

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

Additional parameters always use `name=value`.

## Log kinds
- `REQUEST`
- `RESPONSE`
- `FAULT`
- `EVENT`

## Log levels
- `TRACE`
- `DEBUG`
- `INFO`
- `WARN`
- `ERROR`
- `CRITICAL`

## Payloads

Request, response, and fault payloads are stored as structured JSON and are never flattened for presentation. The Control Center displays them indented and formatted.

## Timing

Nyra tracks `sessionElapsedMs`, `requestElapsedMs`, `traceElapsedMs`, and `spanElapsedMs`.

## Search and navigation

The centralized log viewer supports free-text search and filtering by CT, level, kind, event, result, sessionId, requestId, traceId, and spanId. Identifiers are clickable.

## Ingestion

Logging must not block the request path. Services use a local non-blocking queue and a background worker for batched forwarding to Router. A local spool/retry strategy preserves logs during temporary Router outages.

## Storage

The initial Router implementation uses SQLite in WAL mode. Logs are indexed by timestamp, CT, level, kind, sessionId, requestId, traceId, spanId, and event.

## Security

Secrets must never be persisted. Sensitive parameter names such as authorization, token, api_key, password, secret, and cookie are automatically redacted before persistence or forwarding.
