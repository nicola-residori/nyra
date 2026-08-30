# Architecture Decision Records

## ADR-001 - Router is the central trust boundary
**Status:** Accepted

## ADR-002 - No lateral first-level service communication
**Status:** Accepted

Skills, Memory, Voice, and LLM must not communicate directly with each other. Private implementation dependencies are allowed.

## ADR-003 - Protected capabilities are owned by Router
**Status:** Accepted

Services do not receive Home Assistant credentials or other protected external service credentials. They request capabilities from Router.

## ADR-004 - Operational context is resolved for every request
**Status:** Accepted

Entity aliases, custom names, mappings, and other deterministic operational context must always be available during request interpretation.

## ADR-005 - Semantic memory enrichment is conditional
**Status:** Accepted

Long-term semantic memory is retrieved only when relevant. A downstream component may request additional memory only through Router.

## ADR-006 - Centralized administration and observability
**Status:** Accepted

Router exposes the only Nyra administration and observability interface. Independent service UIs will be removed.

## ADR-007 - Centralized structured logging
**Status:** Accepted

All Nyra services send structured logs to Router.

## ADR-008 - Distributed tracing identifiers
**Status:** Accepted

Nyra logging uses `sessionId`, `requestId`, `traceId`, `spanId`, `parentSpanId`, and `originRequestId`.

`spanId` format: `CT#operation#random`.

Examples: `ROUTER#request_ingress#8F3A12`, `SKILLS#execute#73F0C1`, `MEMORY#context_resolve#02AA91`.

## ADR-009 - Structured log event types
**Status:** Accepted

Each log record has a `kind`: `REQUEST`, `RESPONSE`, `FAULT`, or `EVENT`. Log levels are `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, and `CRITICAL`. Additional parameters use `name=value`. JSON payloads remain structured and are pretty-printed in the UI.

## ADR-010 - Timing metrics
**Status:** Accepted

Nyra tracks elapsed time in milliseconds for session, request, trace, and span.

## ADR-011 - Repository is the project source of truth
**Status:** Accepted

Chat conversations are not persistent technical documentation. Architecture decisions, deployment procedures, configuration, source code, and current project state must be committed while the project is built.

## ADR-012 - Repository content is written in English
**Status:** Accepted

Source code, comments, documentation, configuration examples, API names, log events, and commit messages are written in English.
