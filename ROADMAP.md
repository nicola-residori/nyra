# Nyra Roadmap

## Milestone 1 - Router foundation and observability

**Status: Complete**

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

**Status: Complete**

- Thin native Home Assistant conversation integration
- Synchronous request forwarding to Router
- Source and conversation metadata
- Authenticated Home Assistant user context
- Stable ESPHome speaker `source_id` and deterministic device discovery
- Router event bridge for real-time speaker interaction state
- ESPHome status-ring ownership and semantic LED feedback
- Protected identity feedback: recognized, unrecognized, and identity changed
- TTS playback lifecycle feedback
- Session-close audio/visual feedback
- Custom local `Nyra` wake word
- Physical end-to-end speaker validation

## Milestone 3 - Identity and Voice

**Status: Complete**

- Dedicated Speaker-ID service integrated exclusively through Router
- Parallel, correlated speaker identification audio streams
- Trusted identity context with per-wake-word session boundaries
- Voice-profile enrollment from Home Assistant
- Editable Wake Word sample collection and `.tar.gz` export
- Identity/profile/diagnostic administration through Nyra Admin
- Runtime threshold, margin, and timeout configuration
- Identity observability, metrics, retention, and localized responses
- Reproducible Debian 12 CT deployment and reboot persistence verification

## Milestone 4 - Memory and context

**Status: Complete and deployed in production**

- Operational context resolution
- Structured aliases and mappings
- Semantic memory gate
- Long-term memory enrichment
- Identity-aware memory scopes
- Dedicated SQLite/WAL Memory service with local multilingual embeddings
- Deterministic USER → FAMILY → SYSTEM operational precedence
- Explicit semantic lifecycle: confirm, supersede, and physical deletion
- Conditional NONE / OPTIONAL / REQUIRED semantic-memory gate
- Router-only management API and Nyra Admin memory pages
- Reproducible Debian 12 bootstrap, verification, backup, and restore

## Milestone 5 - Skills

**Status: Complete and deployed in production**

- Dedicated deterministic `nyra-skills` service on the Nyra v1 protocol
- Router-only capability access; Skills contains no direct Home Assistant credentials
- Router-owned Home Assistant resolve, execute, and managed-automation gateway
- Deterministic Home Assistant actions with target clarification
- Restart-safe persisted ephemeral jobs
- Persistent and one-shot Behaviors materialized as Nyra-managed Home Assistant automations
- Explicit remember, forget, and supersede Skills through the Router-owned Memory gateway
- Distributed Router/Skills/capability observability and correlation
- Router-backed Skills/Jobs diagnostics in Nyra Admin
- Removal of standalone Skills UI
- Reproducible bootstrap, verification, backup, guarded restore, and production validation

## Milestone 6 - LLM

**Status: Complete and deployed in production; final merge authorization pending**

- Dedicated first-level `nyra-llm` service behind the Router trust boundary
- Typed `SEMANTIC` and buffered `REASONING` contracts
- Provider-independent `ProviderAdapter` with provider/model routing owned by `nyra-llm`
- Technical/contract-only provider fallback
- Deterministic Skills MISS -> semantic bridge -> general reasoning routing
- Router-owned bounded conversation history, clarification, budgets, and timeout
- Router-mediated read-only `SEARCH_MEMORY`, `READ_STATE`, `READ_ATTRIBUTE`, and `DISCOVER_RESOURCES`
- Mandatory LLM proposal -> Skills validation/materialization -> Router capability action gate
- Privacy-safe distributed LLM observability and Router-backed Admin diagnostics
- Selectable centralized log export and correlated Router/Skills/Memory/LLM traces
- Reproducible systemd/bootstrap/backup/restore/verification assets and production validation

## Milestone 7 - Productization

- Complete Proxmox deployment scripts
- Bootstrap automation
- Installation documentation
- Configuration examples
- Migration documentation
- Reproducible clean installation
