# Nyra Roadmap

## Milestone 1 - Router foundation and observability
- Router application skeleton
- Configuration system
- Health endpoint
- Logging and tracing protocol v1
- SQLite WAL log storage
- Log ingestion API
- Central Control Center
- Logs, Sessions, Requests, Traces, and Services pages
- Structured JSON request/response/fault viewer
- Search and filtering
- Elapsed timing at session/request/trace/span level

## Milestone 2 - Home Assistant adapter
- Thin Home Assistant integration
- Request forwarding to Router
- Source metadata
- Home Assistant user identity
- Speaker/device metadata
- Conversation metadata

## Milestone 3 - Identity and Voice
- Voice service integration through Router
- Parallel speaker identification
- Trusted identity context
- Identity-aware policies

## Milestone 4 - Memory and context
- Operational context resolution
- Structured aliases and mappings
- Semantic memory gate
- Long-term memory enrichment
- Identity-aware memory scopes

## Milestone 5 - Skills
- Skills migration to Nyra v1 protocol
- Router-only capability access
- Home Assistant capability gateway
- Removal of standalone Skills UI

## Milestone 6 - LLM
- Router-managed LLM access
- Context propagation
- Controlled capability calls
- Provider-independent configuration

## Milestone 7 - Productization
- Complete Proxmox deployment scripts
- Bootstrap automation
- Installation documentation
- Configuration examples
- Migration documentation
- Reproducible clean installation
