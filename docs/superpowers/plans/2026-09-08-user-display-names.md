# Trusted User Display Names Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve Home Assistant user IDs as stable identity keys while exposing the current trusted Home Assistant name to Nyra Admin and downstream response generation.

**Architecture:** Home Assistant resolves names only from its authenticated user objects. Router persists `(provider, user_id) -> display_name`, enriches trusted request context and Speaker-ID management DTOs, and leaves Speaker-ID biometric storage keyed only by `user_id`. Missing names never block voice flows and never cause raw IDs to be spoken to users.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, SQLite, Home Assistant custom integration APIs, Jinja2, pytest

**Spec:** `docs/superpowers/specs/2026-09-08-user-display-name-design.md`

## Global Constraints

- `user_id` remains the stable authorization, biometric, persistence, and correlation key.
- Home Assistant is authoritative for `display_name`; ESPHome and request payload text are never trusted as name sources.
- Router owns the persistent user-reference registry and enrichment policy.
- Speaker-ID receives and stores IDs only; do not add display names to its database or biometric contracts.
- Nyra Admin reads all identity data through Router and cannot rename users.
- Added protocol fields are optional so existing callers and stored data remain compatible.
- Empty names do not erase a previously trusted non-empty value.
- Name synchronization failure never blocks Assist, enrollment, or Wake Word capture.
- General observability payloads do not add display names.
- Deploy only after local verification and explicit approval for Home Assistant and Proxmox changes.

---

### Task 1: Extend Trusted Identity Contracts

**Files:**
- Modify: `shared/protocol/requests.py`
- Modify: `shared/protocol/context.py`
- Modify: `homeassistant/custom_components/nyra/shared/protocol/requests.py`
- Modify: `homeassistant/custom_components/nyra/shared/protocol/context.py`
- Test: `tests/protocol/test_requests.py`
- Test: `tests/protocol/test_context.py`
- Test: `tests/homeassistant/test_ha_shared_protocol_runtime.py`

**Interfaces:**
- Produces: `TrustedIdentity.display_name: str | None`
- Produces: `ResolvedIdentity.display_name: str | None`
- Validation: trim surrounding whitespace, convert an empty value to `None`, reject names longer than 255 characters.

- [ ] **Step 1: Add failing contract tests**

```python
def test_trusted_identity_accepts_an_optional_normalized_display_name():
    identity = TrustedIdentity(
        user_id="ha-user-1", provider="home_assistant",
        confidence=1.0, display_name="  Nicola  ",
    )
    assert identity.display_name == "Nicola"
    assert TrustedIdentity(
        user_id="ha-user-1", provider="home_assistant",
        confidence=1.0, display_name="   ",
    ).display_name is None


def test_resolved_identity_carries_the_presentable_name():
    identity = ResolvedIdentity(
        user_id="ha-user-1", display_name="Nicola",
        resolution_source=IdentityResolutionSource.SPEAKER_IDENTIFICATION,
    )
    assert identity.display_name == "Nicola"
```

Also assert that 256 characters fail validation and that models without
`display_name` still validate.

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
/Users/nicola/Develop/nyra/.venv/bin/python -m pytest \
  tests/protocol/test_requests.py \
  tests/protocol/test_context.py \
  tests/homeassistant/test_ha_shared_protocol_runtime.py -q
```

Expected: failures because the protocol models currently reject or ignore
`display_name`.

- [ ] **Step 3: Add the optional fields and shared validator**

Add this field and validator to both canonical models and synchronize the two
changed modules into the Home Assistant bundled protocol copy:

```python
display_name: str | None = Field(default=None, max_length=255)

@field_validator("display_name")
@classmethod
def normalize_display_name(cls, value):
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
```

- [ ] **Step 4: Run protocol and bundled-runtime tests**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Commit the contract change**

```bash
git add shared/protocol homeassistant/custom_components/nyra/shared/protocol \
  tests/protocol tests/homeassistant/test_ha_shared_protocol_runtime.py
git commit -m "feat: add trusted identity display names"
```

---

### Task 2: Add Router User Reference Persistence and Sync API

**Files:**
- Create: `router/user_directory.py`
- Create: `router/api/users.py`
- Modify: `router/app.py`
- Test: `tests/router/test_user_directory.py`
- Test: `tests/router/test_user_sync_api.py`

**Interfaces:**
- Produces: `UserReference(provider: str, user_id: str, display_name: str, updated_at: datetime)`
- Produces: `UserDirectory.initialize() -> None`
- Produces: `UserDirectory.upsert(provider: str, user_id: str, display_name: str) -> UserReference`
- Produces: `UserDirectory.get(provider: str, user_id: str) -> UserReference | None`
- Produces: authenticated `POST /v1/users/sync` with body `{provider, user_id, display_name}`.

- [ ] **Step 1: Write failing store tests**

```python
def test_user_directory_persists_and_updates_a_trusted_name(tmp_path):
    directory = UserDirectory(tmp_path / "router.db")
    directory.initialize()
    first = directory.upsert("home_assistant", "ha-1", "Nicola")
    second = directory.upsert("home_assistant", "ha-1", "Nicola Residori")
    reopened = UserDirectory(tmp_path / "router.db")
    reopened.initialize()
    assert first.user_id == "ha-1"
    assert second.display_name == "Nicola Residori"
    assert reopened.get("home_assistant", "ha-1").display_name == "Nicola Residori"


def test_empty_name_cannot_erase_a_known_reference(tmp_path):
    directory = UserDirectory(tmp_path / "router.db")
    directory.initialize()
    directory.upsert("home_assistant", "ha-1", "Nicola")
    with pytest.raises(ValueError):
        directory.upsert("home_assistant", "ha-1", "   ")
    assert directory.get("home_assistant", "ha-1").display_name == "Nicola"
```

Cover provider separation and idempotent schema initialization.

- [ ] **Step 2: Run store tests and verify RED**

```bash
/Users/nicola/Develop/nyra/.venv/bin/python -m pytest \
  tests/router/test_user_directory.py -q
```

Expected: import failure because `router.user_directory` does not exist.

- [ ] **Step 3: Implement the SQLite directory**

Use this schema:

```sql
CREATE TABLE IF NOT EXISTS trusted_user_references (
    provider TEXT NOT NULL,
    user_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (provider, user_id)
)
```

Normalize all string inputs, use an injected UTC clock for deterministic
tests, and write the upsert with `ON CONFLICT(provider, user_id) DO UPDATE`.

- [ ] **Step 4: Write failing sync API tests**

```python
def test_authenticated_user_sync_persists_reference(tmp_path):
    settings = RouterSettings(
        database_path=tmp_path / "router.db", ingress_token="secret"
    )
    with TestClient(create_app(settings, audio_sink=object())) as client:
        unauthorized = client.post("/v1/users/sync", json={
            "provider": "home_assistant", "user_id": "ha-1",
            "display_name": "Nicola",
        })
        accepted = client.post(
            "/v1/users/sync",
            headers={"Authorization": "Bearer secret"},
            json={"provider": "home_assistant", "user_id": "ha-1",
                  "display_name": "Nicola"},
        )
        assert unauthorized.status_code == 401
        assert accepted.json()["display_name"] == "Nicola"
```

- [ ] **Step 5: Implement and register the sync API**

Define a Pydantic request DTO with non-empty `provider` and `user_id`, and a
normalized `display_name` limited to 255 characters. Reuse
`router.api.requests._authorized`. Initialize `UserDirectory` inside
Router's lifespan, expose it as `app.state.user_directory`, and include the
new router.

- [ ] **Step 6: Run persistence and API tests**

```bash
/Users/nicola/Develop/nyra/.venv/bin/python -m pytest \
  tests/router/test_user_directory.py \
  tests/router/test_user_sync_api.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit Router user synchronization**

```bash
git add router/user_directory.py router/api/users.py router/app.py \
  tests/router/test_user_directory.py tests/router/test_user_sync_api.py
git commit -m "feat: persist trusted user references"
```

---

### Task 3: Enrich Router Identity Resolution and Downstream Context

**Files:**
- Modify: `router/lifecycle/service.py`
- Modify: `router/app.py`
- Test: `tests/router/test_request_lifecycle.py`
- Test: `tests/router/test_identity_continuity.py`

**Interfaces:**
- Consumes: `TrustedIdentity.display_name`, `UserDirectory.get/upsert`.
- Produces: `RequestContext.identity.display_name` for trusted HA identity, biometric identification, and session continuity.
- Produces: `ContextResult.data["identity"]` with `{user_id, display_name, resolution_source}` for downstream Skills/LLM ports.

- [ ] **Step 1: Add failing lifecycle tests**

Add cases that prove a trusted HA request stores `ha-1 -> Nicola`, a later
speaker identification for `ha-1` resolves `display_name == "Nicola"`, and
a `NOT_RECOGNIZED` continuation carries the same reference. Make the context
test double retain the last identity projection.

Add a privacy assertion that collected general log payloads do not contain the
string `Nicola`.

- [ ] **Step 2: Run lifecycle tests and verify RED**

```bash
/Users/nicola/Develop/nyra/.venv/bin/python -m pytest \
  tests/router/test_request_lifecycle.py \
  tests/router/test_identity_continuity.py -q
```

Expected: failures because the lifecycle has no user directory and resolved
identity lacks a display name.

- [ ] **Step 3: Inject and apply `UserDirectory`**

Extend `RequestLifecycleService.__init__` with:

```python
user_directory: UserDirectory | None = None
```

For trusted HA requests, upsert only when `request.identity.display_name` is
non-empty. For all resolved non-guest identities, look up
`("home_assistant", identity_user_id)`. Pass the resulting name into
`ResolvedIdentity`.

Before invoking Memory, Skills, or LLM ports, add this safe projection to a new
copy of `ContextResult.data`:

```python
data["identity"] = {
    "user_id": request_context.identity.user_id,
    "display_name": request_context.identity.display_name,
    "resolution_source": request_context.identity.resolution_source.value,
}
```

Do not insert the display name into `_log`, identity feedback events, or
persisted `request_states`.

- [ ] **Step 4: Run focused Router tests**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Commit lifecycle enrichment**

```bash
git add router/lifecycle/service.py router/app.py \
  tests/router/test_request_lifecycle.py tests/router/test_identity_continuity.py
git commit -m "feat: enrich trusted identity context"
```

---

### Task 4: Synchronize Authenticated Home Assistant Names

**Files:**
- Create: `homeassistant/custom_components/nyra/users.py`
- Modify: `homeassistant/custom_components/nyra/const.py`
- Modify: `homeassistant/custom_components/nyra/client.py`
- Modify: `homeassistant/custom_components/nyra/conversation.py`
- Modify: `homeassistant/custom_components/nyra/panel.py`
- Modify: `homeassistant/custom_components/nyra/enrollment.py`
- Modify: `homeassistant/custom_components/nyra/wake_word_capture.py`
- Test: `tests/homeassistant/test_users.py`
- Test: `tests/homeassistant/test_client.py`
- Test: `tests/homeassistant/test_conversation_core.py`
- Test: `tests/homeassistant/test_enrollment_panel.py`
- Test: `tests/homeassistant/test_enrollment.py`
- Test: `tests/homeassistant/test_ha_wake_word_capture.py`

**Interfaces:**
- Produces: `AuthenticatedUserReference(user_id: str, display_name: str | None)`.
- Produces: `async_resolve_user_reference(hass, user_id) -> AuthenticatedUserReference` using `hass.auth.async_get_user`.
- Produces: `NyraRouterClient.async_sync_user_reference(reference) -> bool`; returns `False` rather than raising when synchronization is unavailable.
- Produces: `AdapterInput.user_display_name: str | None`.

- [ ] **Step 1: Write failing authenticated-user tests**

```python
@pytest.mark.asyncio
async def test_resolver_reads_name_from_home_assistant_auth_only():
    hass = SimpleNamespace(auth=SimpleNamespace(
        async_get_user=AsyncMock(return_value=SimpleNamespace(
            id="ha-1", name="Nicola"
        ))
    ))
    reference = await async_resolve_user_reference(hass, "ha-1")
    assert reference.user_id == "ha-1"
    assert reference.display_name == "Nicola"
```

Cover missing users and blank names. Verify panel message fields and service
data cannot override the authenticated user's name.

- [ ] **Step 2: Write failing Router-client sync tests**

Assert an authenticated `POST /v1/users/sync` body and verify HTTP/network
failure returns `False` without raising.

- [ ] **Step 3: Run Home Assistant tests and verify RED**

```bash
/Users/nicola/Develop/nyra/.venv/bin/python -m pytest \
  tests/homeassistant/test_users.py \
  tests/homeassistant/test_client.py \
  tests/homeassistant/test_conversation_core.py \
  tests/homeassistant/test_enrollment_panel.py \
  tests/homeassistant/test_enrollment.py \
  tests/homeassistant/test_ha_wake_word_capture.py -q
```

Expected: failures because the resolver, client method, and name propagation do
not exist.

- [ ] **Step 4: Implement trusted resolution and best-effort sync**

Add `USER_SYNC_PATH = "/v1/users/sync"`. Resolve the user from Home Assistant
before building authenticated Assist input. Set:

```python
TrustedIdentity(
    user_id=data.user_id,
    provider="home_assistant",
    confidence=1.0,
    display_name=data.user_display_name,
)
```

On Nyra Config enrollment and Wake Word state requests, use the authenticated
`connection.user` object and call `async_sync_user_reference`. Repeat the
same best-effort sync before starting enrollment or Wake Word capture through
the panel or registered HA services. Continue the requested action when sync
returns `False`.

- [ ] **Step 5: Run Home Assistant tests**

Run the command from Step 3. Expected: all selected tests pass.

- [ ] **Step 6: Run the complete Home Assistant regression suite**

```bash
/Users/nicola/Develop/nyra/.venv/bin/python -m pytest tests/homeassistant -q
```

Expected: all Home Assistant tests pass, including M2 speaker behavior.

- [ ] **Step 7: Commit Home Assistant synchronization**

```bash
git add homeassistant/custom_components/nyra tests/homeassistant
git commit -m "feat: sync home assistant user names"
```

---

### Task 5: Enrich Router Admin DTOs

**Files:**
- Create: `router/user_enrichment.py`
- Modify: `router/api/speaker_id_admin.py`
- Test: `tests/router/test_speaker_id_admin_api.py`

**Interfaces:**
- Produces: `enrich_profile(profile, directory) -> dict` with `user_display_name`.
- Produces: `enrich_diagnostic(item, directory) -> dict` with `identified_user_display_name`.
- Produces: `enrich_diagnostic_detail(detail, directory) -> dict`, adding `user_display_name` to every candidate.
- Produces: `enrich_wake_word_sample(sample, directory) -> dict` with `user_display_name`.

- [ ] **Step 1: Add failing API enrichment tests**

Seed `UserDirectory` with `home_assistant/ha-1 -> Nicola`. Make the fake
Speaker-ID Admin client return IDs only, then assert:

```python
assert profiles[0]["user_display_name"] == "Nicola"
assert diagnostics[0]["identified_user_display_name"] == "Nicola"
assert detail["candidates"][0]["user_display_name"] == "Nicola"
assert wake_words[0]["user_display_name"] == "Nicola"
```

Also assert an unknown ID receives `None` and all existing
delete/audio/export routes remain unchanged.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
/Users/nicola/Develop/nyra/.venv/bin/python -m pytest \
  tests/router/test_speaker_id_admin_api.py -q
```

Expected: assertions fail because Router currently proxies Speaker-ID JSON
unchanged.

- [ ] **Step 3: Implement pure enrichment helpers and apply by endpoint**

Copy upstream dictionaries before adding fields. Resolve only
`provider="home_assistant"`. Apply the matching helper after each JSON GET;
do not change binary or mutation routes and do not alter filter parameters.

- [ ] **Step 4: Run Router Admin tests**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Commit DTO enrichment**

```bash
git add router/user_enrichment.py router/api/speaker_id_admin.py \
  tests/router/test_speaker_id_admin_api.py
git commit -m "feat: enrich identity admin data with names"
```

---

### Task 6: Present Names in Nyra Admin

**Files:**
- Modify: `admin/templates/identity_profiles.html`
- Modify: `admin/templates/identity_diagnostics.html`
- Modify: `admin/templates/wake_words.html`
- Modify: `admin/static/css/admin.css`
- Modify: `tests/admin/test_identity_pages.py`

**Interfaces:**
- Consumes: optional Router fields `user_display_name` and `identified_user_display_name`.
- Presentation rule: visible name first, stable ID as secondary `<code>` text; fall back to ID when no name exists.

- [ ] **Step 1: Add failing rendering tests**

Update fake Router responses with `Nicola` and assert every page contains both
the name and stable ID in distinct elements. Add a missing-name fixture and
assert the ID remains visible without an empty heading.

```python
assert '<h3 class="user-name">Nicola</h3>' in profiles
assert '<code class="user-id">user-nicola</code>' in profiles
assert "Nicola" in diagnostics
assert "Nicola" in wake_words
```

- [ ] **Step 2: Run Admin tests and verify RED**

```bash
/Users/nicola/Develop/nyra/.venv/bin/python -m pytest \
  tests/admin/test_identity_pages.py -q
```

Expected: failures because templates currently render only IDs.

- [ ] **Step 3: Update the three templates and shared styling**

Use this pattern consistently:

```jinja2
<h3 class="user-name">{{ profile.user_display_name or profile.user_id }}</h3>
{% if profile.user_display_name %}
  <code class="user-id">{{ profile.user_id }}</code>
{% endif %}
```

For diagnostic candidates and Wake Word provenance, use the corresponding
optional name field and keep the ID next to it for analysis.

- [ ] **Step 4: Run Admin tests**

Run the command from Step 2. Expected: all selected tests pass.

- [ ] **Step 5: Commit Admin presentation**

```bash
git add admin/templates admin/static/css/admin.css tests/admin/test_identity_pages.py
git commit -m "feat: show user names in identity admin"
```

---

### Task 7: Verify Compatibility, Privacy, and Deployment Readiness

**Files:**
- Create: `tests/integration/test_user_display_name_flow.py`
- Modify: `docs/state/CURRENT_STATE.md`
- Test: existing full repository suite.

**Interfaces:**
- Produces: repository state ready for controlled Router/Admin/Home Assistant deployment.
- Leaves firmware and Speaker-ID service code unchanged.

- [ ] **Step 1: Add an integration test for an existing profile**

Create an ID-only fake Speaker-ID profile before syncing a user reference.
Assert Admin initially receives `user_display_name: null`, call
`POST /v1/users/sync`, and assert the same profile then receives `Nicola`
without changing the Speaker-ID record.

- [ ] **Step 2: Run protocol, Router, Home Assistant, and Admin suites**

```bash
/Users/nicola/Develop/nyra/.venv/bin/python -m pytest \
  tests/protocol tests/router tests/homeassistant tests/admin -q
```

Expected: all selected suites pass.

- [ ] **Step 3: Run complete repository verification**

```bash
/Users/nicola/Develop/nyra/.venv/bin/python -m pytest -q
git diff --check
python3 -m compileall -q shared router homeassistant/custom_components/nyra admin
```

Expected: zero test failures, no whitespace errors, and successful Python
bytecode compilation.

- [ ] **Step 4: Review privacy and service scope**

```bash
rg -n "display_name" speaker-id
rg -n "display_name" router/observability router/storage
git diff --stat main...HEAD
```

Expected: no `display_name` changes in Speaker-ID, no new
general-observability serialization, and only intentional M3 files in the
branch diff.

- [ ] **Step 5: Update current-state documentation**

Record that local implementation is verified but not yet deployed. Do not mark
the physical smoke test complete before deployment.

- [ ] **Step 6: Commit verification documentation**

```bash
git add docs/state/CURRENT_STATE.md tests/integration/test_user_display_name_flow.py
git commit -m "test: verify trusted user display names"
```

- [ ] **Step 7: Request the external deployment gate**

Present the exact Router/Admin files for CT 108 and Home Assistant integration
files to deploy. Wait for explicit approval before copying or restarting
services.

- [ ] **Step 8: After approval, deploy and run the physical smoke test**

Verify in order:

1. Router `/health` and `/ready` return HTTP 200.
2. Home Assistant configuration check succeeds and Core restarts normally.
3. Opening Nyra Config as Nicola synchronizes the existing profile.
4. Nyra Admin shows `Nicola` as primary label and the HA ID as secondary text
   in profiles, diagnostics, candidates, and Wake Word samples.
5. A successful Mansarda identification produces trusted context containing
   `user_id` and `display_name="Nicola"`.
6. The response layer receives the name needed to answer “Chi sono?” naturally;
   if the production response specialist is not yet migrated, record that
   response wording as its later integration smoke test rather than adding a
   hardcoded Router answer.

- [ ] **Step 9: Commit deployment evidence and push**

Update `docs/state/CURRENT_STATE.md` with measured results, then run:

```bash
git add docs/state/CURRENT_STATE.md
git commit -m "docs: record user display name validation"
git push origin m3-identity-voice
```
