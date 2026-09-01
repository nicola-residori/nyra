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

## ADR-005 - Semantic memory enrichment is conditional
**Status:** Accepted

## ADR-006 - Centralized administration and observability
**Status:** Accepted

## ADR-007 - Centralized structured logging
**Status:** Accepted

## ADR-008 - Distributed tracing identifiers
**Status:** Accepted

Nyra logging uses `sessionId`, `requestId`, `traceId`, `spanId`, `parentSpanId`, and `originRequestId`. `spanId` format: `CT#operation#random`.

## ADR-009 - Structured log event types
**Status:** Accepted

Each log record has a `kind`: `REQUEST`, `RESPONSE`, `FAULT`, or `EVENT`. Log levels are `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, and `CRITICAL`.

## ADR-010 - Timing metrics
**Status:** Accepted

Nyra tracks elapsed time in milliseconds for session, request, trace, and span.

## ADR-011 - Repository is the project source of truth
**Status:** Accepted

Chat conversations are not persistent technical documentation. Architecture decisions, deployment procedures, configuration, source code, and current project state must be committed while the project is built.

## ADR-012 - Repository content is written in English
**Status:** Accepted

## ADR-013 - Nyra Admin is a separate application
**Status:** Accepted

Nyra Admin is a separate application from Router, communicates through Router APIs, and must not access Router databases directly.

## ADR-014 - Initial Router and Admin ports
**Status:** Accepted

Initial deployment uses Router `:8090` and Admin `:80`; they remain separate processes/services.

## ADR-015 - Home Assistant is a thin platform adapter
**Status:** Accepted

Home Assistant translates platform-specific conversation, authenticated user, source, speaker, and TTS information at the Nyra boundary. Router remains authoritative for orchestration, request lifecycle, traces, semantic interaction state, policies, identity outcomes, and protected capabilities. Speaker source and human identity are separate.

## ADR-016 - Speaker real-time state uses the Router event stream
**Status:** Accepted

Request/response transport and real-time speaker feedback are separate paths. Router semantic events are bridged through Home Assistant to the exact ESPHome speaker identified by stable `source_id`. Actual TTS playback and protected identity transients may temporarily take precedence over semantic state.

## ADR-017 - Nyra speaker source IDs are stable and read-only
**Status:** Accepted

Every Nyra ESPHome speaker exposes a read-only diagnostic `Nyra Source ID`, the deterministic join key between Router source metadata and the Home Assistant device.

## ADR-018 - Custom wake-word models are local speaker assets
**Status:** Accepted

Nyra speakers may include repository-managed ESPHome micro-wake-word manifests and model binaries. Public configuration must not embed installation-specific room inventory, network addresses, credentials, or secrets.
