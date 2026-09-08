# Milestone 5 — Skills Design

**Project:** N.Y.R.A. — Neural sYstem for Reasoning & Automation
**Milestone:** 5 — Skills
**Status:** Approved design
**Date:** 2026-09-08
**Authoritative dependencies:** `ARCHITECTURE.md`, `DECISIONS.md`,
`docs/superpowers/specs/2026-08-31-component-contract-v1-design.md`,
`docs/superpowers/specs/2026-08-30-request-lifecycle-v1-design.md`,
`docs/superpowers/specs/2026-09-08-milestone-4-memory-and-context-design.md`,
and `docs/state/CURRENT_STATE.md`.

## 1. Purpose

Milestone 5 migrates the Skills domain to the Nyra v1 architecture.

M5 delivers a dedicated `nyra-skills` first-level service, deterministic Skill
dispatch, Router-owned Home Assistant capabilities, Nyra v1 execution planning,
clarification-safe target resolution, delayed/ephemeral jobs, platform-neutral
Behaviors for persistent house automation, natural-language Memory management,
centralized observability, Nyra Admin integration, and reproducible deployment.

M5 does not implement the reasoning LLM. It prepares and tests the mandatory
Skills action-gate path that Milestone 6 will use for LLM-proposed
`ExecutionPlan` objects.

## 2. Governing architectural rules

The Router remains Nyra's central trusted orchestration, policy, capability, and
observability boundary.

First-level components do not communicate laterally.

Therefore these paths are forbidden:

```text
Skills -> Home Assistant
Skills -> Memory
Skills -> Speaker-ID
Skills -> LLM provider
Skills -> arbitrary HTTP capability
```

Protected access instead uses:

```text
Skills -> Router -> Home Assistant
Skills -> Router -> Memory
Skills -> Router -> LLM (semantic interpretation, when M6 exists)
```

`nyra-skills` receives only the typed context and correlation required by the
Skills contract. It does not own authoritative session state, trusted identity,
policy, area provenance, or Home Assistant credentials.

Router knows the `nyra-skills` service, never individual Skill modules.

## 3. Current repository baseline

At the start of M5, the repository contains no migrated `nyra-skills` service:
the `skills/` tree is only a placeholder.

Router currently uses the temporary Router-local `IdentityQuerySkill` through
its `SkillPort`. This implementation is a transitional compatibility behavior
and will be moved behind the M5 Skills boundary without changing its observable
language or identity safety behavior.

The shared protocol already contains the v1 foundations for:

- `RequestContext`;
- `SemanticResult`;
- `ExecutionPlan` and execution results;
- `Behavior`;
- Home Assistant capability resolution/execution primitives;
- `MemoryRequirement`;
- common outcomes, correlation, service health and readiness.

M5 extends these contracts only where a Skills-specific typed API is missing.
It does not duplicate them.

## 4. Skills responsibilities

`nyra-skills` owns:

- deterministic Skill registry and dispatch;
- deterministic interpretation for supported commands;
- optional semantic interpretation request construction;
- validation and materialization of `ExecutionPlan`;
- mandatory validation gate for LLM-proposed action plans;
- semantic compatibility checks between operation and resource type;
- deciding whether work is immediate, an ephemeral Skill job, or a persistent
  Home Assistant Behavior;
- ephemeral job persistence and restart safety;
- natural-language interpretation of structured Memory-management commands;
- its own health/readiness and technical observability.

`nyra-skills` does not own:

- trusted identity resolution;
- authoritative request/session/clarification state;
- Home Assistant credentials;
- Home Assistant entity resolution implementation;
- Home Assistant native service translation;
- Memory persistence/admission policy;
- LLM provider/model selection;
- user-facing global reasoning;
- Speaker-ID;
- ESPHome behavior;
- standalone administration UI.

## 5. Skills service API

M5 introduces focused `/v1/...` APIs. Exact payload types live in
`shared/protocol/skills.py`.

Conceptually:

```text
GET  /health
GET  /ready

POST /v1/skills/check
POST /v1/skills/execute
POST /v1/skills/plans/validate-execute

GET  /v1/jobs
GET  /v1/jobs/{job_id}
POST /v1/jobs/{job_id}/cancel
POST /v1/jobs/{job_id}/stop
```

There is no universal Skills payload and no module-specific public endpoint.

Skills-specific request/check/execute/job contracts live in a focused
`shared/protocol/skills.py` module. Existing domain contracts remain in their
own protocol modules:

```text
shared/protocol/skills.py       # Skills service API contracts
shared/protocol/execution.py    # ExecutionPlan and execution contracts
shared/protocol/behavior.py     # Behavior contracts
shared/protocol/capabilities.py # Router capability contracts
```

M5 extends those modules where required rather than moving all payloads into one
file.

### 5.1 Check outcomes

The service returns exactly:

```text
HANDLED
MISS
NEEDS_CLARIFICATION
FAILED
```

The Router rule is strict:

```text
HANDLED             -> do not call reasoning LLM
NEEDS_CLARIFICATION -> do not call reasoning LLM
FAILED              -> do not call reasoning LLM
MISS                -> reasoning LLM may be called
```

Only `MISS` permits automatic LLM fallback.

### 5.2 Conversation statelessness

Skills is conversation-stateless.

If clarification is needed, Skills returns a typed pending-state payload for the
Router to persist. The continuation re-enters Skills with the Router-owned
pending state, the same session/request identifiers, and a new trace.

Skills does not create or persist conversational sessions.

## 6. Internal Skill registry

Skill modules are statically deployed and discovered through a private registry.

Each module has stable metadata such as:

```text
skill_id
version
priority
supported_languages
supported_domains
```

Dispatch is deterministic. A registry conflict at the same effective priority
is a configuration/readiness error rather than an arbitrary winner.

A Skill module interface conceptually provides:

```text
check(...)
execute(...)
```

and may additionally expose plan-validation/materialization helpers where
appropriate.

Individual Skill modules never expose HTTP endpoints.

## 7. Initial migrated Skill set

M5 must provide a narrow but representative set rather than recreating every
possible Home Assistant domain.

The initial required set is:

1. identity query behavior migrated from Router;
2. deterministic Home Assistant action commands for the shared v1 operation
   vocabulary where the resource type supports them;
3. delayed action behavior such as “turn on X and turn it off after N”;
4. persistent/scheduled Behavior construction where the request is not strictly
   ephemeral;
5. natural-language explicit Memory management: remember, forget/delete, and
   structured supersession where unambiguous.

Additional convenience Skills are deferred unless required by these flows.

## 8. Home Assistant Capability Gateway

### 8.1 Ownership

The Router owns Home Assistant protected capabilities.

`nyra-skills` never receives the Home Assistant URL/token and cannot emit raw
Home Assistant service calls.

Router configuration may contain the protected Home Assistant connection
credentials required by its capability adapter.

### 8.2 Router capability interfaces

The target logical API includes:

```text
POST /v1/capabilities/home-assistant/resolve
POST /v1/capabilities/home-assistant/execute
POST /v1/capabilities/home-assistant/automations/create
POST /v1/capabilities/home-assistant/automations/read
POST /v1/capabilities/home-assistant/automations/update
POST /v1/capabilities/home-assistant/automations/delete
```

These endpoints use typed Nyra models. There is no raw service escape hatch.

### 8.3 Home Assistant transport strategy

The default implementation is a Router-owned Home Assistant API client.

For ordinary discovery/state and service execution, Router uses stable Home
Assistant APIs and translates Nyra operations to platform-native calls
internally.

For automation CRUD, the implementation remains behind a narrow
`HomeAssistantCapabilityPort`.

If supported Home Assistant APIs provide the required stable CRUD semantics,
Router uses them directly. If they do not, M5 may add a minimal extension to the
existing Home Assistant Nyra adapter, but only after:

1. a focused RED proves the missing capability;
2. the required HA change is reviewed explicitly;
3. the change remains transport/capability-only and does not introduce
   interpretation or orchestration into HA.

This avoids speculative Home Assistant modification while preserving the M5
Behavior requirement.

## 9. Entity/resource resolution

Home Assistant entity resolution belongs to Router.

Skills sends a semantic reference, expected Nyra resource type, and cardinality.

For `ONE`:

```text
one candidate     -> RESOLVED
multiple valid    -> AMBIGUOUS
zero valid        -> NOT_FOUND
```

`MANY` must be requested explicitly by Skills.

Resolution considers Router-owned policy and trusted context. A resolved target
is stable for one execution and is not silently substituted before side effect.

Skills performs semantic compatibility checks; Router revalidates existence,
availability, supported operation, and policy immediately before execution.

## 10. ExecutionPlan handling

`ExecutionPlan` remains the platform-neutral operational representation already
defined by Component Contract v1.

The approved Component Contract permits an ExecutionPlan to contain both
immediate `steps[]` and future `behaviors[]`. The repository baseline at the
start of M5 implements only `steps[]`, so M5 must close this protocol gap.

The target conceptual model is:

```text
ExecutionPlan
- plan_id
- origin
- validation_state
- steps[]
- behaviors[]
```

The shared protocol implementation must preserve clean module boundaries and
must not create a circular dependency between `execution.py` and `behavior.py`.
The concrete refactor is selected during the RED/GREEN slice and kept minimal;
shared execution primitives may be extracted only if necessary to make both
contracts depend in one direction.

Skills-originated plans are constructed and validated by Skills.

Milestone 6 LLM plans will arrive as:

```text
origin=REASONING_LLM
validation_state=PROPOSED
```

and must pass through Skills before any side effect.

The mandatory path is:

```text
LLM proposed plan
-> Router
-> Skills validate/materialize
-> Router capability
-> external side effect
```

No Router shortcut may execute a proposed LLM side-effect plan without Skills.

### 10.1 Step execution

Dependencies form an acyclic graph.

Failed dependencies produce `SKIPPED_DEPENDENCY`. Failed conditions produce
`SKIPPED_CONDITION`. Independent branches may continue.

M5 does not implement a distributed transaction or global rollback.

Overall execution may be `COMPLETED` or `PARTIALLY_COMPLETED`.

## 11. Idempotency and uncertain outcomes

Conceptually idempotent operations remain:

```text
TURN_ON
TURN_OFF
OPEN
CLOSE
SET
```

Non-idempotent operations include:

```text
TOGGLE
INCREASE
DECREASE
TRIGGER
```

Router must not blindly retry an uncertain non-idempotent Home Assistant
execution.

An uncertain result is represented as `UNKNOWN_OUTCOME`.

Skills does not perform semantic retries.

## 12. Immediate work, Skill jobs, and Behaviors

Runtime destination is based on semantics, not on an arbitrary duration
threshold.

### 12.1 Ephemeral Skill job

A strictly short-lived interaction effect may remain in Skills.

Example:

```text
turn on the light, wait 20 seconds, turn it off
```

when the behavior is intentionally ephemeral and should not become persistent
house configuration.

### 12.2 Home Assistant Behavior

Future, scheduled, recurring, or event-driven house behavior becomes a
platform-neutral `Behavior` and is materialized as a Nyra-managed Home Assistant
automation.

Examples:

```text
turn the porch light on every day at sunset
when the door opens, turn on the hall light
tomorrow at 07:30 start ...
```

There is no “N minutes” threshold separating Job and Behavior.

## 13. Skill jobs

Jobs use persistent SQLite/WAL storage owned by `nyra-skills`.

Lifecycle:

```text
SCHEDULED -> CANCELLED
SCHEDULED -> RUNNING -> COMPLETED
                     -> FAILED
                     -> STOPPED
                     -> UNKNOWN_OUTCOME
```

Requirements:

- scheduled jobs survive service restart;
- overdue scheduled jobs run as soon as practical and record observable delay;
- a job found `RUNNING` after restart becomes `UNKNOWN_OUTCOME`;
- a running job is never blindly re-executed after restart;
- `CANCEL` prevents a scheduled job from starting;
- `STOP` terminates an active effect only when the operation supports it;
- delayed user-originated activity uses `origin_request_id`;
- no active conversational session is fabricated for a job.

## 14. Behaviors and Home Assistant automations

Nyra-created automations carry `managed_by=NYRA`.

Nyra may inspect, execute as permitted by contract, modify, and delete only
Nyra-managed automations.

Manual Home Assistant automations are discoverable/readable but not
controllable or mutable by Nyra.

Manual editing of a Nyra-managed automation does not remove Nyra ownership.
Before modification, Nyra reads the current HA representation.

A probable equivalent manual automation prevents silent duplication and
returns `NEEDS_CLARIFICATION`.

For Nyra-managed `ONE_SHOT` automation:

```text
WAITING -> RUNNING
success -> physically DELETE
failure -> KEEP with observable error
```

## 15. Memory-management Skills

M4 intentionally left natural-language Memory management to M5.

M5 handles explicit user commands such as:

```text
remember that ...
forget ...
replace/update that memory ...
```

Skills interprets the command and creates a structured Memory operation.

Router remains authoritative for trusted identity, scope/admission/policy and
calls Memory. Skills never calls Memory directly.

Deletion or supersession requires an unambiguous target. Semantic similarity
alone never authorizes a destructive mutation.

If multiple plausible memories remain, Skills returns
`NEEDS_CLARIFICATION`. If none exists, it returns the appropriate typed
not-found functional result.

## 16. Memory enrichment gate

The existing M4 `MemoryRequirement` behavior remains authoritative.

A Skill check declares:

```text
NONE
OPTIONAL
REQUIRED
```

Router decides whether to perform semantic-memory search before Skill execution.

M5 does not introduce blind semantic-memory search after every request.

## 17. Identity query migration

The existing Router-local `IdentityQuerySkill` is moved behind the
`nyra-skills` boundary.

Its user-visible behavior remains unchanged:

- use trusted resolved identity only;
- never speak technical user IDs;
- never speak the literal `guest`;
- respond in request language;
- no semantic-memory requirement;
- no Home Assistant capability.

After migration Router no longer has a production built-in Skill implementation.

## 18. Observability

Every Skills and Router capability operation uses normal Nyra distributed
correlation.

Skills logs its own spans with:

```text
request_id?
origin_request_id?
trace_id
parent_span_id
span_id
```

Router centrally reconstructs authoritative session correlation.

Required observable operations include at least:

```text
skills.check
skills.execute
skills.plan.validate
skills.plan.execute
skills.job.schedule
skills.job.start
skills.job.complete
skills.job.fail
skills.job.cancel
skills.job.stop
ha.resolve
ha.execute
ha.automation.create
ha.automation.update
ha.automation.delete
```

Logs never persist Home Assistant credentials or sensitive headers.

The speaker-facing interaction vocabulary remains semantic:

- local deterministic Skills processing uses `PROCESSING_LOCAL`;
- protected capability execution may transiently use `USING_TOOL`;
- internal Skill module names are observability detail, not speaker states.

## 19. Readiness

`nyra-skills /health` means process/HTTP liveness.

`nyra-skills /ready` requires:

- schema/storage initialized;
- registry valid;
- scheduler initialized;
- no deterministic registry conflict;
- essential local execution engine available.

Skills readiness does not require Home Assistant, Memory, or LLM to be healthy,
because those are Router-owned protected dependencies.

Router readiness in M5 includes the required first-level service dependencies
configured for production, including Skills.

Home Assistant capability dependency failures are returned as typed functional
unavailability for capability execution and are observable.

## 20. Nyra Admin

Nyra Admin remains the only administration UI.

M5 adds Router-backed views for useful operational inspection, such as:

- Skills service status;
- registered Skill metadata;
- recent Skill executions;
- Skill jobs and lifecycle status;
- Nyra-managed Home Assistant automations/Behaviors where useful;
- capability failures and ambiguity diagnostics.

Admin never reads Skills SQLite directly and never receives Home Assistant
credentials.

Any standalone legacy Skills UI is not migrated and is removed from the final
production architecture.

## 21. Deployment

`nyra-skills` is deployed as a dedicated Debian 12 service/container following
the same reproducibility discipline used for Speaker-ID and Memory.

The repository must provide, as applicable:

```text
deploy/bootstrap/skills.sh
deploy/systemd/nyra-skills.service
deploy/verify/skills.sh
deploy/backup/skills.sh
deploy/restore/skills.sh
docs/deployment/SKILLS.md
```

Persistent data is stored outside the repository checkout.

Deployment is not authorized until local implementation and regression are
complete.

Before production modification:

1. capture service/container configuration;
2. back up existing legacy Skills state if present;
3. define rollback;
4. verify target ports/paths;
5. deploy only after explicit authorization.

Production validation must include real Home Assistant actions, ambiguity,
delayed work, restart persistence, and rollback readiness.

## 22. Test-driven development

Every executable behavior in M5 follows strict:

```text
RED -> GREEN -> REFACTOR
```

A RED must fail before production implementation and for the expected reason.

The RED test remains permanently in the suite.

Documentation-only changes do not invent artificial RED tests.

Each completed functional slice runs:

1. focused test;
2. component regression;
3. relevant cross-component regression;
4. `git diff --check`;
5. diff inspection;
6. commit only after green verification.

Full repository tests run at integration checkpoints and before deployment.

## 23. Proposed implementation slices

### Task 1 — Shared protocol gaps required by M5

Add only the missing protocol required by M5:

- Skills request/check/execute/validation/job contracts;
- `ExecutionPlan.behaviors[]` required by the approved Component Contract;
- typed Home Assistant automation CRUD capability contracts.

Preserve focused protocol modules rather than introducing a universal Skills
payload. Any refactor needed to avoid an `execution.py` / `behavior.py` import
cycle must remain minimal and protocol-only.

**RED:** imports/schema tests fail because the required Skills models,
ExecutionPlan Behavior support, and automation capability contracts do not yet
exist.

### Task 2 — Service skeleton and readiness

Create `nyra-skills`, health/readiness, configuration, and storage bootstrap.

**RED:** Skills health/readiness tests fail because the service does not exist.

### Task 3 — Deterministic registry

Add private static registry with stable metadata and deterministic dispatch.

**RED:** registry dispatch/conflict tests fail without a registry.

### Task 4 — Router Skills client and lifecycle migration

Replace Router-local production Skill implementation with the dedicated service
client while preserving the `SkillPort` lifecycle semantics.

**RED:** lifecycle integration test proves Router still uses the local Skill and
cannot call a Skills service.

### Task 5 — Exact outcome routing

Implement `HANDLED`, `MISS`, `NEEDS_CLARIFICATION`, `FAILED`.

**RED:** tests prove non-MISS outcomes incorrectly reach the LLM placeholder.

### Task 6 — Home Assistant resolve capability

Implement Router-owned typed resource resolution.

**RED:** resolve endpoint/port tests fail for RESOLVED, AMBIGUOUS, NOT_FOUND,
ONE/MANY semantics.

### Task 7 — Home Assistant execute capability

Implement typed Nyra operation execution and immediate revalidation.

**RED:** TURN_ON/OFF/etc. capability tests fail; include unknown-outcome tests
for uncertain non-idempotent transport.

### Task 8 — Identity Skill migration

Move identity query behavior to `nyra-skills`.

**RED:** end-to-end lifecycle test expects the same localized result through the
service and fails while Router-local Skill is still required.

### Task 9 — Deterministic HA action Skill

Interpret supported direct commands, resolve targets through Router, build and
execute plans.

**RED:** a direct command cannot currently produce and execute a validated
ExecutionPlan through capability mediation.

### Task 10 — Target clarification

Support ambiguous resolution and continuation via Router-owned pending state.

**RED:** two valid resources currently cannot produce a resumable
`NEEDS_CLARIFICATION`.

### Task 11 — Multi-step plan execution

Execute dependency-aware plans and partial completion.

**RED:** dependency failure / independent branch / partial completion cases fail.

### Task 12 — Ephemeral jobs

Add persistent job scheduler and restart semantics.

**RED:** scheduled persistence, overdue execution, cancel, stop, and
RUNNING-after-restart UNKNOWN_OUTCOME tests fail.

### Task 13 — Behavior materialization

Create Nyra-managed Home Assistant automations for persistent/scheduled/event
behavior using the typed automation capability contracts introduced in Task 1.

Validate that `ExecutionPlan.behaviors[]` and standalone Behavior
materialization follow the same Router-owned capability boundary.

**RED:** Behavior cannot currently be materialized through Router capability.

If direct Router-to-HA automation CRUD is insufficient, this task is the gate
where a separately reviewed thin HA adapter extension may be introduced.

### Task 14 — Memory-management Skills

Implement explicit remember/forget/supersede natural-language command handling.

**RED:** explicit memory commands are currently MISS and destructive ambiguity
is not handled by Skills.

### Task 15 — Observability

Add child Skills and Router HA-capability spans with authoritative correlation.

**RED:** a distributed session query currently lacks the new Skills/capability
operations.

### Task 16 — Admin

Add Router-backed Skills/jobs diagnostics and remove reliance on legacy Skills
UI.

**RED:** Admin route/page tests fail because no Skills pages/API aggregation
exist.

### Task 17 — Deployment assets

Add bootstrap/systemd/verify/backup/restore.

**RED:** deployment contract tests fail because required assets are absent or
incomplete.

### Task 18 — Integration regression

Add simulated end-to-end M5 suite covering:

- HANDLED/MISS/FAILED/clarification;
- identity query;
- direct HA action;
- ambiguous target;
- multi-step plan;
- delayed job;
- restart safety;
- persistent Behavior;
- explicit Memory management;
- capability unavailable and unknown-outcome cases;
- distributed observability.

### Task 19 — Production deployment

After explicit authorization:

- backup;
- deploy;
- health/readiness;
- real HA action tests;
- ambiguity test;
- delayed job;
- Behavior;
- persistence across reboot;
- rollback verification where applicable.

### Task 20 — Milestone closure

Run full suite and static/deployment checks; update documentation,
`docs/state/CURRENT_STATE.md` and `ROADMAP.md`; commit/push; verify clean `main`
aligned with `origin/main`.

## 24. Explicitly out of scope

M5 does not implement:

- reasoning LLM;
- provider/model selection;
- `MEMORY_EXTRACTION`;
- Speaker-ID model/threshold/enrollment changes;
- wake-word changes;
- ESPHome changes;
- unrelated Home Assistant UI/device changes;
- new Memory storage semantics beyond M4 contracts;
- service-to-service auth or mTLS;
- clustering/failover;
- general M7 productization;
- raw Home Assistant service escape hatches;
- arbitrary Skills HTTP capabilities;
- standalone Skills administration UI.

## 25. Acceptance criteria

M5 is complete only when all of the following are true:

1. `nyra-skills` is a dedicated Nyra v1 first-level service.
2. Router has no production built-in Skill implementation.
3. Skills cannot access Home Assistant or Memory directly.
4. Router-only HA resolve/execute capability access is enforced by architecture
   and tests.
5. Only `MISS` permits automatic reasoning fallback.
6. Deterministic direct Home Assistant actions execute end to end.
7. Ambiguous targets create Router-owned clarification.
8. ExecutionPlan dependencies and partial completion are tested.
9. Ephemeral jobs survive restart safely and never blindly rerun an uncertain
   active operation.
10. Persistent/scheduled/event-driven behavior becomes Nyra-managed Home
    Assistant automation.
11. Explicit natural-language Memory management works through Router.
12. Skills and capability activity is reconstructable in central observability.
13. Nyra Admin is the only Skills administration surface.
14. Deployment, backup, restore/rollback, and reboot behavior are verified.
15. Full Nyra regression is green.
16. Production is physically validated after explicit authorization.
17. Documentation, `CURRENT_STATE.md`, and `ROADMAP.md` are aligned.
18. `main` is clean and aligned to `origin/main`.
