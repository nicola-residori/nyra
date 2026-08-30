# Router Logging and Nyra Admin v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production Nyra v1 milestone: an independently deployed Router on port 8090 with structured logging/tracing storage and APIs, plus an independently deployed Nyra Admin on port 80 that consumes Router APIs.

**Architecture:** `nyra-router` is the trusted observability backend and owns identifier creation, validation, redaction, SQLite WAL persistence, query APIs, and service health data. `nyra-admin` is a separate FastAPI application with server-rendered HTML/CSS/vanilla JavaScript and never accesses Router storage directly. Shared protocol and logging code lives under `shared/` so later Nyra services can emit the same structured records.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, Pydantic v2, httpx, SQLite, Jinja2, vanilla JavaScript/CSS, pytest.

**Spec:** `docs/specs/2026-08-30-router-logging-admin-v1-design.md`

## Global Constraints

- Nyra Router listens on port `8090`.
- Nyra Admin listens on port `80`.
- Router and Admin are separate applications, processes, configuration objects, and systemd services.
- Nyra Admin communicates with Router exclusively through Router APIs and never opens Router SQLite databases.
- No deployment-specific IP address or credential is hardcoded in source.
- Configuration precedence is environment variables > configuration file > safe defaults.
- SQLite runs in WAL mode.
- `spanId` format is `CT#operation#random`.
- Log kinds are `REQUEST`, `RESPONSE`, `FAULT`, and `EVENT`.
- Log levels are `TRACE`, `DEBUG`, `INFO`, `WARN`, `ERROR`, and `CRITICAL`.
- Request/response/fault payloads remain structured JSON.
- Secret fields are redacted before persistence.
- Logging transport must not block functional request execution.
- Repository source, comments, documentation, configuration names, APIs, event names, and commit messages are English.

---

## File Structure

```text
router/
├── __init__.py
├── app.py
├── config.py
├── api/
│   ├── __init__.py
│   ├── health.py
│   ├── logs.py
│   └── observability.py
├── observability/
│   ├── __init__.py
│   ├── ids.py
│   ├── redaction.py
│   └── service.py
└── storage/
    ├── __init__.py
    └── sqlite.py

admin/
├── __init__.py
├── app.py
├── config.py
├── client.py
├── routes/
│   ├── __init__.py
│   └── pages.py
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── logs.html
│   ├── requests.html
│   ├── sessions.html
│   ├── traces.html
│   └── services.html
└── static/
    ├── css/admin.css
    └── js/logs.js

shared/
├── __init__.py
├── protocol/
│   ├── __init__.py
│   └── observability.py
└── logging/
    ├── __init__.py
    └── client.py

tests/
├── router/
│   ├── test_health.py
│   ├── test_ids.py
│   ├── test_redaction.py
│   ├── test_storage.py
│   ├── test_log_ingestion.py
│   └── test_observability_queries.py
├── admin/
│   ├── test_health.py
│   ├── test_client.py
│   └── test_pages.py
└── shared/
    ├── test_protocol.py
    └── test_logging_client.py

deploy/
├── bootstrap/router.sh
├── systemd/nyra-router.service
└── systemd/nyra-admin.service

pyproject.toml
config.example.yaml
.env.example
```

### Task 1: Shared Observability Protocol and Identifier Generation

**Files:**
- Create: `shared/__init__.py`
- Create: `shared/protocol/__init__.py`
- Create: `shared/protocol/observability.py`
- Create: `router/observability/__init__.py`
- Create: `router/observability/ids.py`
- Create: `tests/shared/test_protocol.py`
- Create: `tests/router/test_ids.py`
- Create/Modify: `pyproject.toml`

**Interfaces:**
- Produces: `LogLevel`, `LogKind`, `LogRecord`, `LogBatch`, `generate_session_id()`, `generate_request_id()`, `generate_trace_id()`, `generate_span_id(ct: str, operation: str)`.
- Consumes: nothing from later tasks.

- [ ] **Step 1: Add project dependencies and pytest configuration**

Create `pyproject.toml` with Python `>=3.11` and runtime dependencies `fastapi`, `uvicorn`, `pydantic>=2`, `httpx`, `jinja2`, `pyyaml`, plus pytest test dependencies.

- [ ] **Step 2: Write failing protocol and ID tests**

Test exact enum membership, JSON-compatible payload preservation, required identifier fields, ID prefixes `ses_`, `req_`, `trc_`, and a span regex equivalent to:

```python
r"^[A-Z0-9_-]+#[a-z0-9_]+#[A-Z0-9]{8}$"
```

Also test that invalid levels/kinds fail Pydantic validation.

- [ ] **Step 3: Run the focused tests**

Run:

```bash
pytest tests/shared/test_protocol.py tests/router/test_ids.py -v
```

Expected: FAIL because protocol and identifier modules do not exist.

- [ ] **Step 4: Implement the protocol**

Implement string enums and Pydantic models. `LogRecord` must include:

```text
schema_version
timestamp
ct
level
kind
event
session_id
request_id
trace_id
span_id
parent_span_id
origin_request_id
operation
result
message
session_elapsed_ms
request_elapsed_ms
trace_elapsed_ms
span_elapsed_ms
params
payload
```

Optional fields use `None`; `params` defaults to `{}`; payload accepts JSON-compatible object/list/scalar/null.

- [ ] **Step 5: Implement identifier generation**

Use cryptographically secure randomness for the span suffix and UUID/ULID-like collision-resistant values for the three primary IDs. Normalize CT to uppercase and operation to lowercase snake-compatible text before formatting the span.

- [ ] **Step 6: Run focused tests**

Run the same pytest command. Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml shared router/observability tests/shared tests/router/test_ids.py
git commit -m "feat(protocol): add observability contracts and identifiers"
```

### Task 2: Secret Redaction

**Files:**
- Create: `router/observability/redaction.py`
- Create: `tests/router/test_redaction.py`

**Interfaces:**
- Produces: `redact(value: Any, sensitive_keys: set[str] | None = None) -> Any`.
- Consumes: JSON-compatible values from `LogRecord.params` and `LogRecord.payload`.

- [ ] **Step 1: Write failing redaction tests**

Cover nested dictionaries, dictionaries inside lists, mixed-case keys, default sensitive keys, configured additional keys, and preservation of non-sensitive values.

Expected sensitive names include:

```text
authorization
token
api_key
password
secret
cookie
```

Expected replacement is exactly `***REDACTED***`.

- [ ] **Step 2: Run the focused test**

```bash
pytest tests/router/test_redaction.py -v
```

Expected: FAIL because `redact` does not exist.

- [ ] **Step 3: Implement recursive redaction**

Redact before storage. Key matching is case-insensitive. Do not mutate the caller's original object.

- [ ] **Step 4: Run the focused test**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add router/observability/redaction.py tests/router/test_redaction.py
git commit -m "feat(logging): add recursive secret redaction"
```

### Task 3: SQLite WAL Log Storage

**Files:**
- Create: `router/storage/__init__.py`
- Create: `router/storage/sqlite.py`
- Create: `tests/router/test_storage.py`

**Interfaces:**
- Produces: `SQLiteObservabilityStore(path: Path)`, `.initialize()`, `.insert_logs(records)`, `.query_logs(filters)`, `.get_request(id)`, `.get_session(id)`, `.get_trace(id)`, `.list_requests(filters)`, `.list_sessions(filters)`, `.list_traces(filters)`.
- Consumes: validated `LogRecord` instances.

- [ ] **Step 1: Write failing storage tests**

Use a temporary database. Verify:

```sql
PRAGMA journal_mode
```

returns `wal`, records survive reopening, JSON payloads round-trip structurally, and filters work for CT, level, kind, event, session ID, request ID, trace ID, span ID, result, and timestamp range.

- [ ] **Step 2: Test aggregate views**

Insert a small synthetic session with two requests, multiple traces and spans. Assert request/session/trace summaries contain counts, start/end timestamps, result, and elapsed values.

- [ ] **Step 3: Run focused tests**

```bash
pytest tests/router/test_storage.py -v
```

Expected: FAIL because storage is not implemented.

- [ ] **Step 4: Implement schema and indexes**

Create a `logs` table with scalar searchable columns and JSON text columns for `params` and `payload`. Create indexes for timestamp, CT, level, kind, event, session ID, request ID, trace ID, and span ID.

Keep schema creation idempotent.

- [ ] **Step 5: Implement insert and query methods**

Use parameterized SQL only. Decode JSON columns before returning data.

Free-text search searches event/message/operation/result and serialized params/payload.

- [ ] **Step 6: Implement aggregate request/session/trace queries**

Derive v1 summaries from structured log records instead of adding redundant aggregate tables.

- [ ] **Step 7: Run focused tests**

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add router/storage tests/router/test_storage.py
git commit -m "feat(router): add SQLite observability storage"
```

### Task 4: Router Configuration and Health API

**Files:**
- Create: `router/__init__.py`
- Create: `router/config.py`
- Create: `router/api/__init__.py`
- Create: `router/api/health.py`
- Create: `router/app.py`
- Create: `tests/router/test_health.py`
- Create: `config.example.yaml`
- Create: `.env.example`

**Interfaces:**
- Produces: `RouterSettings`, `create_app(settings: RouterSettings | None = None) -> FastAPI`, `GET /health`.
- Consumes: `SQLiteObservabilityStore`.

- [ ] **Step 1: Write failing configuration and health tests**

Verify defaults use host `0.0.0.0`, port `8090`, and a non-hardcoded database path. Verify environment variables override YAML/defaults.

Verify `/health` returns JSON with `service`, `version`, `status`, `uptime`, and `timestamp`.

- [ ] **Step 2: Run focused tests**

```bash
pytest tests/router/test_health.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement Router settings**

Support safe defaults, optional YAML, and environment overrides. Do not include actual deployment IPs or secrets in tracked files.

- [ ] **Step 4: Implement Router app factory and health endpoint**

Initialize the store during application lifespan. Health must be lightweight and not query downstream services.

- [ ] **Step 5: Run focused tests**

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add router config.example.yaml .env.example tests/router/test_health.py
git commit -m "feat(router): add configuration and health API"
```

### Task 5: Log Ingestion API

**Files:**
- Create: `router/observability/service.py`
- Create: `router/api/logs.py`
- Modify: `router/app.py`
- Create: `tests/router/test_log_ingestion.py`

**Interfaces:**
- Produces: `POST /v1/logs/ingest`.
- Consumes: `LogBatch`, `redact()`, `SQLiteObservabilityStore.insert_logs()`.

- [ ] **Step 1: Write failing ingestion tests**

Cover a valid batch, a single-record compatibility payload, invalid level, invalid kind, malformed span ID, missing event, redaction before persistence, and structured rejection details.

- [ ] **Step 2: Add partial-batch test**

Submit one valid and one malformed record. Assert the response identifies the rejected item and does not silently discard it. Define v1 semantics as atomic validation: if any record is invalid, persist none.

- [ ] **Step 3: Run focused tests**

```bash
pytest tests/router/test_log_ingestion.py -v
```

Expected: FAIL.

- [ ] **Step 4: Implement ingestion service**

Validate all records, redact params/payload, then persist the validated batch in one transaction.

- [ ] **Step 5: Implement API route**

Return explicit counts and validation details. Keep endpoint versioned at `/v1/logs/ingest`.

- [ ] **Step 6: Run focused tests**

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add router/observability/service.py router/api/logs.py router/app.py tests/router/test_log_ingestion.py
git commit -m "feat(router): add structured log ingestion API"
```

### Task 6: Router Observability Query APIs

**Files:**
- Create: `router/api/observability.py`
- Modify: `router/app.py`
- Create: `tests/router/test_observability_queries.py`

**Interfaces:**
- Produces:
  - `GET /v1/logs`
  - `GET /v1/requests`
  - `GET /v1/requests/{request_id}`
  - `GET /v1/sessions`
  - `GET /v1/sessions/{session_id}`
  - `GET /v1/traces`
  - `GET /v1/traces/{trace_id}`
  - `GET /v1/spans/{span_id}`
  - `GET /v1/services`
- Consumes: `SQLiteObservabilityStore` query methods.

- [ ] **Step 1: Write failing API query tests**

Seed synthetic observability records and verify all listed routes, pagination, exact identifier filters, free-text search, and timestamp filtering.

- [ ] **Step 2: Verify trace detail behavior**

Assert trace detail returns chronological logs plus a span hierarchy containing parent relationships and timing fields.

- [ ] **Step 3: Run focused tests**

```bash
pytest tests/router/test_observability_queries.py -v
```

Expected: FAIL.

- [ ] **Step 4: Implement query routes**

Use explicit query parameters and bounded pagination. Return structured JSON only.

- [ ] **Step 5: Implement initial service registry view**

At this milestone `/v1/services` includes Router and configured service endpoints/health metadata without credentials. It must be extensible for later service health polling.

- [ ] **Step 6: Run focused tests**

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add router/api/observability.py router/app.py tests/router/test_observability_queries.py
git commit -m "feat(router): expose observability query APIs"
```

### Task 7: Shared Non-Blocking Logging Client

**Files:**
- Create: `shared/logging/__init__.py`
- Create: `shared/logging/client.py`
- Create: `tests/shared/test_logging_client.py`

**Interfaces:**
- Produces: `NyraLogger`, context binding, queue-backed batching, local bounded spool, retry.
- Consumes: Router `POST /v1/logs/ingest` contract and shared protocol models.

- [ ] **Step 1: Write failing logger tests**

Verify automatic context injection, semantic event calls, batch flush by count, batch flush by interval, HTTP failure fallback to spool, successful retry, bounded spool behavior, and that logging calls return without waiting for network completion.

- [ ] **Step 2: Run focused tests**

```bash
pytest tests/shared/test_logging_client.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement context-bound logger**

Provide an API that lets application code emit events without manually repeating IDs.

- [ ] **Step 4: Implement background batching**

Use an in-process queue and worker. Default batch size and flush interval come from configuration rather than hardcoded deployment values.

- [ ] **Step 5: Implement bounded spool and retry**

Use a local file-based spool suitable for service restart recovery. Apply redaction before enqueue/transport so secrets are never written to spool.

- [ ] **Step 6: Run focused tests**

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shared/logging tests/shared/test_logging_client.py
git commit -m "feat(logging): add non-blocking Nyra logging client"
```

### Task 8: Nyra Admin Foundation

**Files:**
- Create: `admin/__init__.py`
- Create: `admin/config.py`
- Create: `admin/client.py`
- Create: `admin/routes/__init__.py`
- Create: `admin/routes/pages.py`
- Create: `admin/app.py`
- Create: `admin/templates/base.html`
- Create: `admin/templates/dashboard.html`
- Create: `admin/static/css/admin.css`
- Create: `tests/admin/test_health.py`
- Create: `tests/admin/test_client.py`

**Interfaces:**
- Produces: `AdminSettings`, `RouterClient`, `create_app()`, `GET /health`, `GET /`.
- Consumes: Router HTTP APIs only.

- [ ] **Step 1: Write failing Admin health/config tests**

Verify default port is `80`, Router URL is configuration-driven, and Admin health succeeds independently of Router.

- [ ] **Step 2: Write failing RouterClient tests**

Mock Router responses and network failures. Ensure network errors become a typed unavailable state rather than crashing page rendering.

- [ ] **Step 3: Run focused tests**

```bash
pytest tests/admin/test_health.py tests/admin/test_client.py -v
```

Expected: FAIL.

- [ ] **Step 4: Implement Admin settings and Router client**

Use `httpx.AsyncClient`. Do not import Router storage modules.

- [ ] **Step 5: Implement Admin app and base template**

Create a persistent navigation shell for Dashboard, Logs, Requests, Sessions, Traces, and Services. Show a global Router connectivity indicator.

- [ ] **Step 6: Implement initial Dashboard**

Display Router/Admin health and summary counters obtained from Router APIs. Render a clear Router-unavailable state when necessary.

- [ ] **Step 7: Run focused tests**

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add admin tests/admin
git commit -m "feat(admin): add standalone Nyra Admin foundation"
```

### Task 9: Nyra Admin Logs Viewer

**Files:**
- Create: `admin/templates/logs.html`
- Create: `admin/static/js/logs.js`
- Modify: `admin/routes/pages.py`
- Modify: `admin/static/css/admin.css`
- Create: `tests/admin/test_pages.py`

**Interfaces:**
- Produces: `GET /logs` and browser-side filtering/navigation behavior.
- Consumes: Router `GET /v1/logs`.

- [ ] **Step 1: Write failing Logs page smoke tests**

Verify the rendered page contains controls for free text, CT, level, kind, event, result, session ID, request ID, trace ID, span ID, time range, and live mode.

- [ ] **Step 2: Add JSON rendering and identifier-navigation tests**

Verify payload containers preserve structured JSON and identifier links carry the correct filter parameter.

- [ ] **Step 3: Run focused tests**

```bash
pytest tests/admin/test_pages.py -v
```

Expected: FAIL.

- [ ] **Step 4: Implement Logs page**

Render timestamp, CT, level, kind, session/request/trace/span IDs, event, result, and elapsed values. Use stable CSS classes per CT, kind, and level.

- [ ] **Step 5: Implement JSON detail expansion**

Use browser-side pretty printing with two-space indentation. Never insert payload JSON using unsafe HTML; render it as text content.

- [ ] **Step 6: Implement live mode**

Use lightweight polling against Router-backed Admin routes for v1. Keep the JavaScript interface isolated so Server-Sent Events can replace polling later without changing page semantics.

- [ ] **Step 7: Run focused tests**

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add admin/templates/logs.html admin/static admin/routes/pages.py tests/admin/test_pages.py
git commit -m "feat(admin): add centralized log viewer"
```

### Task 10: Requests, Sessions, Traces, Spans, and Services Pages

**Files:**
- Create: `admin/templates/requests.html`
- Create: `admin/templates/sessions.html`
- Create: `admin/templates/traces.html`
- Create: `admin/templates/services.html`
- Modify: `admin/routes/pages.py`
- Modify: `admin/static/css/admin.css`
- Modify: `tests/admin/test_pages.py`

**Interfaces:**
- Produces: human-facing observability navigation.
- Consumes: Router observability query APIs.

- [ ] **Step 1: Write failing page tests**

Verify list/detail navigation for requests, sessions, and traces; span parent/child information; timing fields; and service health state.

- [ ] **Step 2: Add trace-tree test**

Seed a trace with parent and child spans and verify the rendered trace page exposes hierarchy and elapsed timing.

- [ ] **Step 3: Run focused tests**

Expected: FAIL.

- [ ] **Step 4: Implement Requests and Sessions pages**

Provide chronological drill-down and clickable identifiers.

- [ ] **Step 5: Implement Traces and span detail**

Render chronological events plus a timing-oriented hierarchical view sufficient to identify slow spans.

- [ ] **Step 6: Implement Services page**

Show endpoint, health, last successful check, last error, and latency where Router provides them. Never display credentials.

- [ ] **Step 7: Run focused tests**

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add admin/templates admin/routes/pages.py admin/static/css/admin.css tests/admin/test_pages.py
git commit -m "feat(admin): add observability drill-down pages"
```

### Task 11: Reproducible Debian/Systemd Deployment

**Files:**
- Create: `deploy/bootstrap/router.sh`
- Create: `deploy/systemd/nyra-router.service`
- Create: `deploy/systemd/nyra-admin.service`
- Modify: `docs/DEPLOYMENT.md`
- Modify: `docs/state/CURRENT_STATE.md`

**Interfaces:**
- Produces: reproducible Router/Admin deployment into the Debian 12 CT.
- Consumes: repository application code and environment/config files.

- [ ] **Step 1: Write bootstrap verification commands into the deployment doc**

Document commands that prove Python version, venv installation, systemd status, Router port 8090, Admin port 80, and both health endpoints.

- [ ] **Step 2: Implement bootstrap script**

The script must be idempotent and install only required Debian packages, create/update the venv, install the project, create runtime data directories, and install systemd units.

Do not embed deployment-specific IPs or credentials.

- [ ] **Step 3: Implement separate systemd units**

`nyra-router.service` starts Router on `0.0.0.0:8090`.

`nyra-admin.service` starts Admin on `0.0.0.0:80`.

Both run as `root` for the current Nyra deployment convention and have independent restart policies.

- [ ] **Step 4: Validate shell syntax**

```bash
bash -n deploy/bootstrap/router.sh
```

Expected: no output and exit code 0.

- [ ] **Step 5: Run the full automated test suite**

```bash
pytest -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deploy docs
git commit -m "chore(deploy): add Router and Admin deployment"
```

### Task 12: Milestone Verification and State Update

**Files:**
- Modify: `docs/state/CURRENT_STATE.md`
- Modify: `ROADMAP.md` if milestone status is represented there.

**Interfaces:**
- Produces: verified Milestone 1 state.
- Consumes: all prior tasks.

- [ ] **Step 1: Run all tests**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 2: Verify Router locally**

Start Router and verify:

```bash
curl -fsS http://127.0.0.1:8090/health
```

Expected: structured healthy JSON.

- [ ] **Step 3: Verify Admin locally**

Start Admin with permission to bind port 80 and verify:

```bash
curl -fsS http://127.0.0.1/health
```

Expected: structured healthy JSON.

- [ ] **Step 4: Ingest a synthetic distributed trace**

Create one session/request/trace with at least Router and Skills-style spans and REQUEST, EVENT, RESPONSE records. Submit through `/v1/logs/ingest`.

- [ ] **Step 5: Verify observability APIs**

Query the synthetic data by session ID, request ID, trace ID, and span ID and verify timing and JSON payload preservation.

- [ ] **Step 6: Verify Nyra Admin manually**

Open Nyra Admin and confirm:

```text
Dashboard loads
Logs display
CT identities are distinct
REQUEST/RESPONSE/FAULT/EVENT are visually distinct
levels are visually distinct
JSON is pretty-printed
IDs are clickable
filters work
trace hierarchy is visible
elapsed milliseconds are visible
Services page loads
Router-unavailable state is understandable
```

- [ ] **Step 7: Update current state**

Mark Router foundation, logging/tracing, and Nyra Admin v1 as implemented and record the next migration target.

- [ ] **Step 8: Commit milestone state**

```bash
git add docs/state/CURRENT_STATE.md ROADMAP.md
git commit -m "docs: mark Router observability milestone complete"
```

- [ ] **Step 9: Push only after verification**

```bash
git status
git log --oneline -12
git push origin main
```

Expected: clean working tree after push.
