# Nyra Current State

## Version
Nyra v1.0-dev

## Current milestone
Router foundation and centralized observability.

## Infrastructure
A new Nyra Router container has been created.

Environment:
- Hostname: `nyra-router`
- OS: Debian 12
- Python: 3.11
- Service port: `8090`

Network addresses are deployment-specific and must never be hardcoded into source code.

## Completed architecture decisions
- Router is the central orchestration component.
- First-level services know only Router.
- Router owns protected capabilities.
- Operational context is resolved for every request.
- Semantic memory retrieval is conditional.
- Router owns centralized logging and observability.
- Nyra exposes a single administration UI through Router.
- Logging uses sessionId, requestId, traceId and spanId.
- spanId format is `CT#operation#random`.
- Logs distinguish REQUEST, RESPONSE, FAULT and EVENT.
- Request, response, and fault JSON payloads are displayed formatted.
- Session, request, trace, and span elapsed times are tracked in milliseconds.
- Repository content is written in English.

## Existing alpha services
The existing Nyra alpha implementation remains operational while Nyra v1 is developed. Components will be migrated individually only after the Router foundation is stable.

## Next step
Implement Nyra Logging and Tracing Protocol v1 and the Router foundation: application skeleton, configuration loader, health endpoint, structured logging models, SQLite log storage, log ingestion API, central log viewer, and trace/request/session navigation.
