# Milestone 4 Memory and Context Design

## Status and scope

This document defines Milestone 4 of Nyra v1. It is authoritative together
with the Component Contract v1 and the Request Lifecycle v1 design. Where this
document makes an earlier placeholder concrete, this document governs the M4
implementation.

Milestone 4 delivers:

- the `nyra-memory` first-level service;
- deterministic Operational Context resolution;
- structured operational entries of type `ALIAS`, `MAPPING`, `DEFAULT`, and
  `SHORTCUT`;
- persistent Semantic Long-Term Memory;
- conditional semantic-memory enrichment in Router;
- identity-aware `USER`, `FAMILY`, and `SYSTEM` scopes;
- Router-owned management APIs and Nyra Admin pages;
- centralized observability, deployment, backup, and restart verification.

Natural-language commands such as “remember this” and “forget that” remain a
Milestone 5 Skills responsibility. LLM reasoning and asynchronous
`MEMORY_EXTRACTION` remain Milestone 6 work. M4 provides the typed ports and
complete storage operations those milestones will consume.

## Architectural boundaries

Router remains the trusted orchestration, policy, admission, identity, and
observability boundary. All high-level reads and writes enter through Router.
Nyra Admin calls Router and never reads the Memory database or filesystem.

`nyra-memory` owns:

- validation and persistence of Operational Context records;
- deterministic scope resolution and same-scope conflict detection;
- validation and persistence of Semantic Memory records;
- embedding generation through a private provider interface;
- scope-filtered similarity search;
- physical deletion of semantic content and embeddings;
- its own health and readiness state.

`nyra-memory` does not own request/session lifecycle, trusted identity,
authorization policy, semantic admission decisions, user-facing wording,
natural-language interpretation, Skill execution, or LLM prompting.

The production service is a separate process in a dedicated Debian container.
Its canonical store is SQLite in WAL mode on persistent local storage. At the
expected household scale, normalized embedding vectors are stored with the
records and compared in process; M4 does not introduce PostgreSQL, pgvector,
Qdrant, or another database service.

Embedding generation is isolated behind an `EmbeddingProvider` interface.
Production uses the multilingual
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` model on CPU.
Tests use deterministic fakes and never download a model. Every vector stores
the provider and model revision that generated it so a future reindex is
explicit and auditable.

## Shared protocol

The shared protocol gains focused Memory contracts rather than expanding the
generic `OperationalContext.values` placeholder indefinitely.

### Common enums

```text
MemoryScope: USER | FAMILY | SYSTEM
OperationalEntryType: ALIAS | MAPPING | DEFAULT | SHORTCUT
SemanticMemoryType: FACT | PREFERENCE | NOTE | RELATION
SemanticMemorySource: USER_EXPLICIT | IMPORTED | SYSTEM
SemanticMemoryState: ACTIVE | SUPERSEDED | DELETED
MemoryRequirement: NONE | OPTIONAL | REQUIRED
MemoryAdmission: NEW | DUPLICATE | SUPERSEDES
```

`USER` records require `owner_user_id`. `FAMILY` and `SYSTEM` records reject an
owner. In v1, `FAMILY` means the single Nyra household and therefore needs no
separate family identifier.

### Correlation

Interactive calls carry `session_id`, `request_id`, `trace_id`, and a new
operation `span_id`. Delayed activity may carry a null `request_id` and an
`origin_request_id`. Admin operations create a trace and span even when they
have no interactive session. Technical names and events remain English.

## Operational Context

### Record

An operational record contains:

```text
entry_id
entry_type
scope
owner_user_id?
key
value (typed JSON object)
enabled
revision
created_at
updated_at
```

Keys are trimmed, Unicode-normalized, case-folded identifiers. Empty keys and
empty values are rejected. Type-specific payload models reject unknown fields.

- `ALIAS` maps a spoken or symbolic name to one canonical reference.
- `MAPPING` maps one structured value to another structured value.
- `DEFAULT` supplies a value when a request omits it.
- `SHORTCUT` expands to a declarative intent and parameters.

A shortcut cannot contain arbitrary code, loops, URLs, HTTP operations, Home
Assistant service calls, credentials, raw LLM prompts, or direct capability
invocations. Router/Skills must still construct and authorize any later
execution plan.

### Resolution

Operational Context is resolved for every interactive request and every job for
which context applies. Router sends only trusted fields required for resolution:
canonical identity, source ID, area, language, timestamp, and structured lookup
keys.

Resolution uses this precedence:

```text
USER > FAMILY > SYSTEM
```

An identified user may receive their own `USER` records plus `FAMILY` and
`SYSTEM`. An unidentified or guest request receives only `FAMILY` and `SYSTEM`.
Another user's records are never candidates.

One result at the highest matching scope resolves successfully. More than one
incompatible record at that same scope returns `AMBIGUOUS`; lower scopes cannot
break that tie. Disabled records are excluded. The response includes applied
entry IDs and revisions so a decision can be reconstructed from logs.

## Semantic Long-Term Memory

### Record and lifecycle

A semantic record contains:

```text
memory_id
memory_type
scope
owner_user_id?
content
normalized_content
source
state
embedding?
embedding_provider?
embedding_model?
supersedes_memory_id?
created_at
updated_at
last_confirmed_at
```

Active content has no TTL. The general observability retention policy never
removes active or superseded semantic records.

The lifecycle is:

```text
ACTIVE -> SUPERSEDED
ACTIVE -> DELETED
SUPERSEDED -> DELETED
```

Supersession creates a new active record in the same scope and links both
directions transactionally. History remains queryable in Admin but superseded
records are excluded from ordinary retrieval.

Deletion physically removes content, normalized content, embedding, provider,
model, source metadata, and ownership metadata. A minimal tombstone retains
only `memory_id`, state `DELETED`, deletion timestamp, and non-sensitive audit
correlation. Deleted records never appear in search results.

### Admission

Router owns the admission result:

- an exact normalized active match in the same scope and owner is
  `DUPLICATE`; Router updates `last_confirmed_at` without creating a record;
- an explicit, uniquely identified `supersedes_memory_id` is `SUPERSEDES`;
- every other valid structured create is `NEW`.

Similarity alone never causes replacement or deletion. Multiple plausible
targets return `AMBIGUOUS`; no candidate returns `NOT_FOUND`. M4 Admin exposes
explicit structured operations, so no natural-language guess is needed.

Embedding generation and database mutation form one logical write. If a vector
cannot be generated, a semantic create or supersession returns `UNAVAILABLE`
and leaves no partial active record.

### Search and isolation

A search request contains query text, permitted scopes, canonical user ID when
`USER` is permitted, optional memory types, a bounded result count, and a
minimum similarity. The service applies scope and ownership filters before
similarity ranking. It returns active records only, with score, scope, type,
source, timestamps, and model revision.

The service never searches every user's memories and filters afterward. A
request without an identified canonical user cannot request `USER` scope.
Semantic results are advisory; consumers must not treat similarity as identity,
authorization, or permission evidence.

## Router orchestration and gate

The request flow becomes:

```text
request
  -> trusted identity resolution
  -> Operational Context resolution
  -> Skill check
  -> conditional Semantic Memory search
  -> Skill execution or later LLM reasoning
```

`SkillMatch` gains a `MemoryRequirement` and an optional structured memory
query. `NONE` skips search. `OPTIONAL` searches and allows execution without
results if Memory is unavailable. `REQUIRED` searches and returns
`UNAVAILABLE` if the service cannot answer safely.

The existing identity query Skill declares `NONE`. Until Milestones 5 and 6 add
consumers, a Skill miss does not trigger a blind semantic search. Contract and
integration tests use a requesting fake Skill to prove the complete M4 path.
This avoids cost and unrelated-memory disclosure while making the integration
ready for later real consumers.

Router builds the authoritative `RequestContext` from trusted ingress plus the
resolved operational result. Memory never accepts identity or scope claims
directly from Home Assistant or a speaker.

## Service API

The private `nyra-memory` API includes:

```text
GET    /health
GET    /ready
POST   /v1/context/resolve
GET    /v1/operational/entries
POST   /v1/operational/entries
PUT    /v1/operational/entries/{entry_id}
DELETE /v1/operational/entries/{entry_id}
POST   /v1/semantic/search
GET    /v1/semantic/memories
GET    /v1/semantic/memories/{memory_id}
POST   /v1/semantic/memories
POST   /v1/semantic/memories/{memory_id}/confirm
POST   /v1/semantic/memories/{memory_id}/supersede
DELETE /v1/semantic/memories/{memory_id}
```

Router exposes corresponding `/v1/admin/memory/...` management endpoints and
uses a private client for lifecycle resolution and search. Public management
payloads never permit callers to inject trace ownership, trusted identity, or
an admission outcome.

List endpoints use bounded pagination and filters. Mutation endpoints support
an idempotency key. Repeating the same key returns the original result; using
one key with different content returns a conflict.

## Failure behavior

The Router's trusted base context—identity, source, area, language, and time—does
not disappear when Memory is unavailable.

- Operational resolution failure is logged and marked unavailable. A request
  may continue only when its selected route does not depend on operational
  entries.
- Optional semantic search failure is logged and produces no enrichment.
- Required semantic search failure returns `UNAVAILABLE`.
- A synchronous mutation is confirmed only after durable commit.
- Timeout, malformed response, scope violation, and model mismatch remain
  distinct structured error codes.
- Network retries occur only for idempotent reads or mutations carrying an
  idempotency key.

Memory readiness requires an initialized schema, writable database, and a
loaded production embedding provider. Health indicates process liveness only.
Router readiness reports Memory dependency state without making unrelated
Router administration inaccessible.

## Observability

Router and Memory emit correlated operations including:

```text
CONTEXT_RESOLUTION_START
CONTEXT_RESOLUTION_COMPLETED
CONTEXT_RESOLUTION_FAILED
MEMORY_SEARCH_START
MEMORY_SEARCH_COMPLETED
MEMORY_SEARCH_SKIPPED
MEMORY_SEARCH_FAILED
MEMORY_WRITE_COMPLETED
MEMORY_WRITE_FAILED
MEMORY_SUPERSEDED
MEMORY_DELETED
```

Logs contain IDs, types, scopes, result counts, model revision, admission
outcome, and elapsed time. Ordinary logs never contain full semantic content,
embeddings, credentials, or another user's private data. Admin content views
come from authorized Router APIs, not observability payloads.

## Nyra Admin

Nyra Admin adds one `Memory` navigation group with two pages.

### Operational context

The page lists entries with filters for type, scope, owner, key, and enabled
state. It supports create, edit, enable/disable, and delete. It shows canonical
user display names alongside technical IDs and highlights same-scope conflicts.

### Semantic memory

The page supports query search and filters for type, scope, owner, source, and
state. Detail views show content, score when opened from a search, timestamps,
model revision, and supersession history. Actions include create, confirm,
supersede, and delete. Deletion requires the exact record selected in the UI;
the UI never deletes from a free-text similarity result without selection.

Admin remains usable when Memory is down and displays the dependency error
without fabricating empty successful results.

## Persistence, deployment, and recovery

The repository gains reproducible bootstrap, systemd, environment example, and
verification artifacts for a dedicated Debian 12 `nyra-memory` container. The
container ID, IP address, credentials, and installation secrets remain local
deployment configuration and are not committed.

The SQLite database, model cache, and configuration live under persistent
service-owned paths. Deployment preserves an existing database. Schema changes
use explicit forward migrations inside transactions and never recreate a live
database silently.

Backup uses an SQLite-consistent snapshot plus configuration and the exact
embedding model identifier. Restore verification checks record counts,
supersession links, tombstones, model compatibility, and a known semantic
query. Reboot verification checks service readiness and persistence.

No production container creation, installation, restart, or Router/Admin
deployment occurs until local implementation and verification are complete and
the user has authorized that external step.

## Testing and acceptance

Implementation follows strict TDD. Each production behavior begins with a
focused failing test that fails for the missing behavior.

Required coverage includes:

- protocol validation for every enum, payload, scope, owner, and correlation
  rule;
- operational precedence, guest behavior, disabled entries, revisions, and
  same-scope ambiguity;
- declarative shortcut rejection rules;
- semantic create, exact duplicate confirmation, explicit supersession,
  physical deletion, tombstones, and transaction rollback;
- scope filtering before ranking and isolation between at least two users;
- embedding failure, timeout, retry, idempotency, and model revision handling;
- Router gate behavior for `NONE`, `OPTIONAL`, and `REQUIRED`;
- correlated observability without semantic content leakage;
- Admin listing, filtering, detail, mutations, owner display names, and
  dependency failures;
- database migration, process restart, backup, and restore;
- full repository regression.

M4 is complete when all local tests pass, Router uses the production Memory
client instead of stubs, Admin manages both domains through Router, a fresh
container deployment is reproducible, and production restart/persistence
verification passes. Conversational memory management and LLM extraction are
not M4 acceptance criteria.
