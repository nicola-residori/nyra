# Milestone 4 Memory and Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Deliver persistent Operational Context and Semantic Long-Term Memory through a dedicated nyra-memory service, Router orchestration, and Nyra Admin.

**Architecture:** nyra-memory owns SQLite persistence, deterministic resolution, embedding generation, and scope-filtered search. Router owns identity, admission, policy, lifecycle gating, public APIs, and observability. Admin accesses Memory only through Router. Every task follows RED-GREEN TDD and ends with an independently testable commit.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLite/WAL, httpx, sentence-transformers CPU embeddings, Jinja2, vanilla JavaScript, pytest.

**Spec:** docs/superpowers/specs/2026-09-08-milestone-4-memory-and-context-design.md

## Global Constraints

- Operational precedence is exactly USER > FAMILY > SYSTEM; same-scope conflicts are AMBIGUOUS.
- USER records require a canonical Nyra user ID; FAMILY and SYSTEM reject owners.
- Similarity never authorizes destructive mutation.
- Semantic text and embeddings commit atomically; deletion removes sensitive content and ownership.
- Tests use deterministic fake embeddings and never download models.
- Work only on m4-memory-context; do not modify main.
- Do not change Proxmox, Home Assistant, or production before explicit deployment authorization.

---

### Task 1: Typed Memory protocol

**Files:**
- Create: shared/protocol/memory.py
- Modify: shared/protocol/__init__.py
- Create: tests/protocol/test_memory.py
- Modify: tests/protocol/test_contract_invariants.py

**Interfaces:** Produce all Memory enums plus typed operational CRUD/resolution and semantic CRUD/search payloads.

- [ ] **Step 1: Write failing tests**

~~~python
def test_user_scope_requires_owner():
    with pytest.raises(ValidationError):
        OperationalEntryCreate(
            entry_type="ALIAS", scope="USER", key="desk",
            value={"target": "light.office"},
        )

def test_family_scope_rejects_owner():
    with pytest.raises(ValidationError):
        SemanticMemoryCreate(
            memory_type="FACT", scope="FAMILY", owner_user_id="user-1",
            content="The bins go out Tuesday", source="USER_EXPLICIT",
        )
~~~

Also test bounds, normalization, shortcut payloads, forbidden fields, and exports.

- [ ] **Step 2: Run RED**

Run: /Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/protocol/test_memory.py tests/protocol/test_contract_invariants.py -q

Expected: collection fails because shared.protocol.memory is absent.

- [ ] **Step 3: Implement minimal models**

~~~python
class ScopedModel(BaseModel):
    scope: MemoryScope
    owner_user_id: str | None = None

    @model_validator(mode="after")
    def validate_owner(self):
        if (self.scope is MemoryScope.USER) != (self.owner_user_id is not None):
            raise ValueError("USER requires owner; FAMILY/SYSTEM reject owner")
        return self
~~~

Use ConfigDict(extra="forbid") throughout and export all public contracts.

- [ ] **Step 4: Run GREEN:** /Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/protocol -q
- [ ] **Step 5: Commit:** `git add shared/protocol/memory.py shared/protocol/__init__.py tests/protocol/test_memory.py tests/protocol/test_contract_invariants.py && git commit -m "feat: define memory protocol"`

---

### Task 2: Memory service foundation

**Files:**
- Create: memory/__init__.py, memory/config.py, memory/app.py, memory/requirements.txt
- Modify: pyproject.toml
- Create: tests/memory/test_config.py, tests/memory/test_health.py

**Interfaces:** Produce MemorySettings.load(), create_app(), /health, and /ready.

- [ ] **Step 1: Write failing tests**

~~~python
def test_settings_load_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("NYRA_MEMORY_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("NYRA_MEMORY_MODEL", "test-model")
    settings = MemorySettings.load()
    assert settings.database_path == tmp_path / "memory.sqlite3"
    assert settings.embedding_model == "test-model"

def test_ready_requires_store_and_embedder(client):
    response = client.get("/ready")
    assert response.json()["storage"] == "initialized"
    assert response.json()["embedding"] == "loaded"
~~~

- [ ] **Step 2: Run RED:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/memory/test_config.py tests/memory/test_health.py -q`; expect missing Memory package.
- [ ] **Step 3: Implement:** default data root /var/lib/nyra-memory, port 8090, model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2, limit 10, floor 0.35, timeout 3.0 seconds. Lifespan initializes storage and provider before readiness.
- [ ] **Step 4: Run GREEN:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/memory/test_config.py tests/memory/test_health.py -q`
- [ ] **Step 5: Commit:** `git add memory pyproject.toml tests/memory/test_config.py tests/memory/test_health.py && git commit -m "feat: bootstrap nyra memory service"`

---

### Task 3: Operational persistence and resolution

**Files:**
- Create: memory/storage.py, memory/operational.py
- Create: tests/memory/test_operational_store.py, tests/memory/test_operational_resolution.py

**Interfaces:** Produce transactional operational CRUD and OperationalContextService.resolve().

- [ ] **Step 1: Write failing tests**

~~~python
def test_user_wins_over_family_and_system(store, service):
    store.create_operational(alias("SYSTEM", "light.default"))
    store.create_operational(alias("FAMILY", "light.family"))
    store.create_operational(alias("USER", "light.nicola", owner="user-nicola"))
    result = service.resolve(resolve_request(user="user-nicola", keys=["desk"]))
    assert result.values["desk"]["target"] == "light.nicola"

def test_same_scope_conflict_is_ambiguous(store, service):
    store.create_operational(alias("FAMILY", "light.one"))
    store.create_operational(alias("FAMILY", "light.two"))
    assert service.resolve(resolve_request(keys=["desk"])).outcome == "AMBIGUOUS"
~~~

Add guest exclusion, cross-user isolation, disabled entries, revisions, Unicode/case normalization, and shortcut rejection.

- [ ] **Step 2: Run RED:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/memory/test_operational_store.py tests/memory/test_operational_resolution.py -q`; expect missing store/service.
- [ ] **Step 3: Implement:** indexed operational_entries, WAL, foreign keys, BEGIN IMMEDIATE, memop_UUID IDs, allowed-scope filtering before precedence.
- [ ] **Step 4: Run GREEN:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/memory/test_operational_store.py tests/memory/test_operational_resolution.py -q`
- [ ] **Step 5: Commit:** `git add memory/storage.py memory/operational.py tests/memory/test_operational_store.py tests/memory/test_operational_resolution.py && git commit -m "feat: resolve operational context"`

---

### Task 4: Operational Context API

**Files:**
- Create: memory/api/__init__.py, memory/api/operational.py
- Modify: memory/app.py
- Create: tests/memory/test_operational_api.py

**Interfaces:** Produce POST /v1/context/resolve and operational list/create/update/delete endpoints.

- [ ] **Step 1: Write failing endpoint test**

~~~python
def test_resolve_returns_applied_revision(client):
    created = client.post("/v1/operational/entries", json=alias_payload()).json()
    resolved = client.post("/v1/context/resolve", json=resolve_payload()).json()
    assert resolved["applied"][0] == {
        "entry_id": created["entry_id"], "revision": 1,
    }
~~~

Cover NOT_FOUND, AMBIGUOUS, validation, pagination, filters, and idempotency conflicts.

- [ ] **Step 2: Run RED:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/memory/test_operational_api.py -q`
- [ ] **Step 3: Implement:** thin typed routes mapping domain outcomes to stable HTTP responses.
- [ ] **Step 4: Run GREEN:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/memory -q`
- [ ] **Step 5: Commit:** `git add memory/api memory/app.py tests/memory/test_operational_api.py && git commit -m "feat: expose operational context API"`

---

### Task 5: Semantic lifecycle

**Files:**
- Modify: memory/storage.py
- Create: memory/semantic.py, memory/embeddings.py
- Create: tests/memory/test_semantic_store.py, tests/memory/test_semantic_lifecycle.py

**Interfaces:** Produce create(), confirm(), supersede(), delete(), get(), and list(). Produce the `EmbeddingProvider` protocol and `EmbeddingVector`; Task 6 supplies the production implementation.

- [ ] **Step 1: Write failing lifecycle tests**

~~~python
def test_duplicate_confirms_without_new_record(service):
    first = service.create(create_memory("I drink espresso", "key-1"))
    duplicate = service.create(create_memory(" I drink espresso ", "key-2"))
    assert duplicate.admission == "DUPLICATE"
    assert duplicate.memory_id == first.memory_id
    assert service.list().total == 1

def test_delete_leaves_minimal_tombstone(service, raw_row):
    created = service.create(create_memory("Private note", "key-1"))
    service.delete(created.memory_id, "key-2")
    row = raw_row(created.memory_id)
    assert row["state"] == "DELETED"
    assert row["content"] is row["embedding"] is row["owner_user_id"] is None
~~~

Add embed rollback, supersession, invalid states, owner isolation, and idempotency mismatch tests.

- [ ] **Step 2: Run RED:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/memory/test_semantic_store.py tests/memory/test_semantic_lifecycle.py -q`
- [ ] **Step 3: Implement:** semantic_memories, semantic_tombstones, idempotency_results; the provider protocol; normalized-content hash; atomic vector write; atomic supersession; scrubbed deletion.
- [ ] **Step 4: Run GREEN:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/memory/test_semantic_store.py tests/memory/test_semantic_lifecycle.py -q`
- [ ] **Step 5: Commit:** `git add memory/storage.py memory/semantic.py memory/embeddings.py tests/memory/test_semantic_store.py tests/memory/test_semantic_lifecycle.py && git commit -m "feat: persist semantic memory lifecycle"`

---

### Task 6: Embeddings and semantic search

**Files:**
- Modify: memory/embeddings.py
- Modify: memory/semantic.py
- Create: tests/memory/test_embeddings.py, tests/memory/test_semantic_search.py

**Interfaces:** Produce EmbeddingVector, SentenceTransformerEmbeddingProvider, and scope-filtered search().

- [ ] **Step 1: Write failing isolation test**

~~~python
def test_scope_filter_runs_before_ranking(service):
    add_user_memory(service, "user-a", "secret", [1.0, 0.0])
    add_user_memory(service, "user-b", "closer secret", [1.0, 0.0])
    result = service.search(search_for("user-a", [1.0, 0.0]))
    assert [item.owner_user_id for item in result.items] == ["user-a"]
~~~

Cover cosine order, type filters, threshold, top-k, active-only results, model mismatch, zero vectors, and guest scope.

- [ ] **Step 2: Run RED:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/memory/test_embeddings.py tests/memory/test_semantic_search.py -q`
- [ ] **Step 3: Implement:** normalized float32 storage; lifespan model load; asyncio.to_thread inference; SQL scope filtering before stable score-descending, ID-ascending ranking.
- [ ] **Step 4: Run GREEN:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/memory/test_embeddings.py tests/memory/test_semantic_search.py -q`
- [ ] **Step 5: Commit:** `git add memory/embeddings.py memory/semantic.py tests/memory/test_embeddings.py tests/memory/test_semantic_search.py && git commit -m "feat: search scoped semantic memory"`

---

### Task 7: Semantic API and observability

**Files:**
- Create: memory/api/semantic.py, memory/observability.py
- Modify: memory/app.py
- Create: shared/logging/redaction.py
- Modify: shared/logging/client.py, router/observability/redaction.py
- Create: tests/memory/test_semantic_api.py, tests/memory/test_observability.py
- Modify: tests/shared/test_logging_client.py

**Interfaces:** Produce the private semantic endpoints and correlated, redacted events.

- [ ] **Step 1: Write failing redaction test**

~~~python
def test_search_log_excludes_content(client, event_sink):
    client.post("/v1/semantic/search", json=search_payload("espresso"))
    event = event_sink.last("MEMORY_SEARCH_COMPLETED")
    assert event.params["result_count"] == 1
    assert "espresso" not in json.dumps(event.model_dump())
~~~

Cover CRUD/search errors, correlation, elapsed time, and model revision.

- [ ] **Step 2: Run RED:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/memory/test_semantic_api.py tests/memory/test_observability.py -q`
- [ ] **Step 3: Implement:** start/completed/failed events containing IDs, scope/type, counts, outcomes, revision, and elapsed time only. Move generic redaction into shared/logging so Memory can use NyraLogger without importing Router; preserve the Router import as a compatibility re-export.
- [ ] **Step 4: Run GREEN:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/memory -q`
- [ ] **Step 5: Commit:** `git add memory/api/semantic.py memory/observability.py memory/app.py shared/logging/redaction.py shared/logging/client.py router/observability/redaction.py tests/memory/test_semantic_api.py tests/memory/test_observability.py tests/shared/test_logging_client.py && git commit -m "feat: expose semantic memory API"`

---

### Task 8: Router Memory client and context adapter

**Files:**
- Create: router/memory_client.py
- Modify: router/config.py, router/app.py, router/api/health.py
- Create: tests/router/test_memory_client.py, tests/router/test_memory_health.py

**Interfaces:** Produce ContextPort/MemoryPort adapters and management calls; add NYRA_MEMORY_URL and NYRA_MEMORY_TIMEOUT_SECONDS.

- [ ] **Step 1: Write failing correlation test**

~~~python
@pytest.mark.asyncio
async def test_context_client_forwards_correlation(client, request, trace_id):
    result = await client.resolve_context(request, "user-nicola", trace_id)
    assert result.data["aliases"]["desk"] == "light.office"
    assert client.transport.last_request.headers["x-nyra-trace-id"] == trace_id
~~~

Cover malformed responses, timeout, retry boundaries, and health dependency detail.

- [ ] **Step 2: Run RED:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/router/test_memory_client.py tests/router/test_memory_health.py -q`
- [ ] **Step 3: Implement:** bounded httpx client; retry idempotent reads/keyed mutations only; replace app stubs; expose dependency status without disabling Admin.
- [ ] **Step 4: Run GREEN:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/router -q`
- [ ] **Step 5: Commit:** `git add router/memory_client.py router/config.py router/app.py router/api/health.py tests/router/test_memory_client.py tests/router/test_memory_health.py && git commit -m "feat: connect router to memory service"`

---

### Task 9: Conditional semantic-memory gate

**Files:**
- Modify: router/lifecycle/service.py, router/identity_skill.py
- Modify: tests/router/test_request_lifecycle.py
- Create: tests/integration/test_memory_enrichment_flow.py

**Interfaces:** Extend SkillMatch with memory_requirement and memory_query; search only for OPTIONAL or REQUIRED.

- [ ] **Step 1: Write failing gate tests**

~~~python
@pytest.mark.asyncio
async def test_none_skips_memory(lifecycle):
    lifecycle.skill_port.match = SkillMatch(matched=True, memory_requirement="NONE")
    await lifecycle.handle(request)
    assert lifecycle.memory_port.calls == []

@pytest.mark.asyncio
async def test_required_failure_stops_execution(lifecycle):
    lifecycle.skill_port.match = required_memory_match("coffee preference")
    lifecycle.memory_port.error = MemoryUnavailable()
    response = await lifecycle.handle(request)
    assert response.error["code"] == "MEMORY_UNAVAILABLE"
~~~

Also prove OPTIONAL continues empty, identity Skill uses NONE, misses do not search blindly, and trusted identity determines scopes.

- [ ] **Step 2: Run RED:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/router/test_request_lifecycle.py tests/integration/test_memory_enrichment_flow.py -q`
- [ ] **Step 3: Implement:** operational resolve, Skill check without semantic data, allowed-scope derivation, conditional search, then execution.
- [ ] **Step 4: Run GREEN:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/router/test_request_lifecycle.py tests/router/test_identity_response.py tests/integration/test_memory_enrichment_flow.py -q`
- [ ] **Step 5: Commit:** `git add router/lifecycle/service.py router/identity_skill.py tests/router/test_request_lifecycle.py tests/integration/test_memory_enrichment_flow.py && git commit -m "feat: gate semantic memory enrichment"`

---

### Task 10: Router admission and management API

**Files:**
- Create: router/memory_admin.py, router/api/memory_admin.py
- Modify: router/app.py
- Create: tests/router/test_memory_admin_api.py, tests/integration/test_memory_admin_flow.py

**Interfaces:** Produce /v1/admin/memory/operational and /v1/admin/memory/semantic routes. Router decides NEW, DUPLICATE, or SUPERSEDES.

- [ ] **Step 1: Write failing duplicate test**

~~~python
def test_exact_duplicate_is_confirmed(client):
    first = client.post("/v1/admin/memory/semantic", json=create_payload("I prefer espresso")).json()
    duplicate = client.post("/v1/admin/memory/semantic", json=create_payload(" I prefer espresso ")).json()
    assert duplicate["admission"] == "DUPLICATE"
    assert duplicate["memory_id"] == first["memory_id"]
~~~

Cover exact supersession, ambiguous/missing targets, owner authorization/display, pagination, dependency failure, idempotency, and log redaction.

- [ ] **Step 2: Run RED:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/router/test_memory_admin_api.py tests/integration/test_memory_admin_flow.py -q`
- [ ] **Step 3: Implement:** duplicate calls confirm; exact explicit target calls supersede; other valid creates are NEW; never derive destructive targets from similarity; join names through UserDirectory.
- [ ] **Step 4: Run GREEN:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/router tests/integration/test_memory_admin_flow.py -q`
- [ ] **Step 5: Commit:** `git add router/memory_admin.py router/api/memory_admin.py router/app.py tests/router/test_memory_admin_api.py tests/integration/test_memory_admin_flow.py && git commit -m "feat: manage memory through router"`

---

### Task 11: Nyra Admin Memory pages

**Files:**
- Modify: admin/routes/pages.py, admin/templates/base.html, admin/static/css/admin.css
- Create: admin/templates/operational_context.html, admin/templates/semantic_memory.html, admin/static/js/memory.js
- Create: tests/admin/test_memory_pages.py

**Interfaces:** Add /memory/operational, /memory/semantic, and Router-only proxy routes.

- [ ] **Step 1: Write failing name/ID test**

~~~python
def test_semantic_page_shows_name_and_id(client):
    response = client.get("/memory/semantic")
    assert "Nicola Residori" in response.text
    assert "user-nicola" in response.text
~~~

Cover filters, forms, history, scores, mutations, conflicts, dependency errors, and absence of direct Memory URLs.

- [ ] **Step 2: Run RED:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/admin/test_memory_pages.py -q`
- [ ] **Step 3: Implement:** Italian labels, exact selected record for destructive actions, and visible dependency errors through RouterClient.
- [ ] **Step 4: Run GREEN:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/admin -q`
- [ ] **Step 5: Commit:** `git add admin/routes/pages.py admin/templates/base.html admin/templates/operational_context.html admin/templates/semantic_memory.html admin/static/js/memory.js admin/static/css/admin.css tests/admin/test_memory_pages.py && git commit -m "feat: add memory administration"`

---

### Task 12: Deployment, recovery, and acceptance

**Files:**
- Create: deploy/systemd/nyra-memory.service
- Create: deploy/bootstrap/memory.sh, deploy/verify/memory.sh
- Create: deploy/backup/memory.sh, deploy/restore/memory.sh
- Create: docs/deployment/MEMORY.md
- Modify: docs/state/CURRENT_STATE.md, README.md, ROADMAP.md
- Create: tests/tools/test_memory_deployment.py
- Create: tests/integration/test_m4_memory_context_flow.py
- Create: tests/contracts/test_m4_contract_docs.py

**Interfaces:** Produce reproducible Debian 12 deployment, backup/restore, restart verification, and final acceptance.

- [ ] **Step 1: Write failing deployment tests**

~~~python
def test_memory_unit_uses_persistent_paths():
    unit = Path("deploy/systemd/nyra-memory.service").read_text()
    assert "NYRA_MEMORY_DATA_ROOT=/var/lib/nyra-memory" in unit
    assert "User=nyra-memory" in unit

def test_restore_refuses_running_service():
    script = Path("deploy/restore/memory.sh").read_text()
    assert "systemctl is-active --quiet nyra-memory" in script
~~~

The integration test covers operational precedence, semantic lifecycle, two-user isolation, Router OPTIONAL/REQUIRED gates, and Admin retrieval.

- [ ] **Step 2: Run RED:** `/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/tools/test_memory_deployment.py tests/integration/test_m4_memory_context_flow.py tests/contracts/test_m4_contract_docs.py -q`
- [ ] **Step 3: Implement:** locked service user, persistent paths, model cache, systemd unit, SQLite-consistent hashed backup, stopped-service guarded restore, health/readiness/restart verification, and updated state docs.
- [ ] **Step 4: Run local completion checks**

~~~bash
/Users/nicola/Develop/nyra/.venv/bin/python -m pytest -q
git diff --check
~~~

- [ ] **Step 5: Commit:** `git add deploy docs README.md ROADMAP.md tests/tools/test_memory_deployment.py tests/integration/test_m4_memory_context_flow.py tests/contracts/test_m4_contract_docs.py && git commit -m "ops: complete M4 memory deployment"`
- [ ] **Step 6: Obtain deployment authorization:** Present exact container resources, proposed IP/VMID, affected services, backup, and rollback; wait for explicit authorization.
- [ ] **Step 7: Deploy:** After authorization, create the container, bootstrap Memory, configure/deploy Router and Admin, restart affected services, and verify persistence across restart.
- [ ] **Step 8: Record evidence and push:** Update production evidence, rerun the full suite and diff check, commit, and push under the user's standing authorization.
