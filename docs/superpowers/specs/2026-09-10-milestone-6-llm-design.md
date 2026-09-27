# Milestone 6 — LLM Design

**Project:** N.Y.R.A. — Neural sYstem for Reasoning & Automation
**Milestone:** 6 — LLM
**Status:** Approved design
**Date:** 2026-09-10
**Authoritative dependencies:** `ARCHITECTURE.md`, `DECISIONS.md`,
`ROADMAP.md`, `README.md`,
`docs/superpowers/specs/2026-08-31-component-contract-v1-design.md`,
`docs/superpowers/specs/2026-08-30-request-lifecycle-v1-design.md`,
`docs/superpowers/specs/2026-09-08-milestone-4-memory-and-context-design.md`,
`docs/superpowers/specs/2026-09-08-milestone-5-skills-design.md`,
and `docs/state/CURRENT_STATE.md`.

## 1. Purpose

Milestone 6 migrates LLM access and global reasoning to the Nyra v1 architecture.

M6 delivers a dedicated first-level `nyra-llm` service, provider-independent
inference, typed semantic and reasoning contracts, strict Skills MISS routing,
Router-mediated read-only reasoning capabilities, bounded conversation context,
Router-owned clarification state, mandatory Skills validation for LLM-proposed
side effects, provider/model fallback for technical failures only, privacy-safe
observability, token/cost diagnostics, Nyra Admin integration, and reproducible
deployment.

M6 completes the first-level specialist topology defined by the Nyra v1
component contract. It does not move orchestration, policy, trusted identity,
Home Assistant credentials, Memory authorization, or side-effect authority into
the LLM service.

M6 uses buffered responses. End-to-end token streaming is explicitly outside the
milestone, but the contracts and ownership boundaries must not prevent a future
streaming transport.

Automatic persistent memory extraction is also outside M6 production scope.
The `MEMORY_EXTRACTION` purpose remains part of the protocol design, but M6 does
not automatically infer and persist memories from ordinary conversation.

## 2. Governing architectural rules

The Router remains Nyra's central trusted orchestration, policy, capability,
session, clarification, and observability boundary.

First-level specialist services do not communicate laterally.

The target topology is:

```text
Home Assistant
      |
      v
  nyra-router
   /   |    |    \
  v    v    v     v
skills memory speaker-id llm
                       |
                       v
                ProviderAdapter
                       |
                       v
                    LiteLLM
                       |
             +---------+---------+
             v         v         v
           OpenAI   Anthropic  local/other
```

The following paths are forbidden:

```text
LLM -> Home Assistant
LLM -> Memory
LLM -> Skills
LLM -> Speaker-ID
LLM -> arbitrary URL
LLM -> provider-selected Router behavior
LLM -> raw Home Assistant service call
LLM -> direct side effect
LLM -> direct Memory mutation
```

Protected access instead uses:

```text
LLM -> NEEDS_CAPABILITY -> Router -> authorized read-only capability
LLM -> proposed ExecutionPlan -> Router -> Skills -> Router capability
```

`nyra-llm` never receives Home Assistant credentials, Memory service
credentials, or an unrestricted network capability.

## 3. Current repository baseline

At the start of M6, `main` already contains the completed and production-deployed
M5 architecture.

The Router lifecycle already checks Skills before global reasoning and already
contains an `LlmPort` abstraction. The application wiring still uses a temporary
LLM stub rather than a production `nyra-llm` client.

The shared protocol already contains the Nyra v1 foundations required by M6,
including:

- `RequestContext`;
- trusted identity and policy context;
- `SemanticResult`;
- `ExecutionPlan`;
- `PlanOrigin.REASONING_LLM`;
- proposed versus validated execution state;
- common lifecycle/correlation models;
- Skills check outcomes;
- Router-owned capability primitives.

M5 also introduced `LlmActionGate`, proving the mandatory future action path:

```text
LLM proposal
 -> Skills validation/materialization
 -> Router-owned capability
 -> optional Home Assistant side effect
```

At the start of M6, that gate is a safety scaffold rather than a complete
end-to-end LLM action path. M6 must wire the real LLM proposal flow through the
gate and close any missing Skills plan-validation API needed to make the
architecture executable.

The repository contains no production `nyra-llm` first-level service, provider
adapter implementation, model registry, LLM deployment unit, or Router LLM
configuration.

## 4. M6 architectural ownership

### 4.1 Router owns

The Router remains authoritative for:

- request/session lifecycle;
- trusted `RequestContext`;
- trusted identity and identity continuity;
- policy enforcement;
- routing decisions;
- the strict Skills-to-LLM transition;
- bounded conversation history;
- clarification state;
- reasoning round-trip budget;
- end-to-end reasoning timeout;
- capability allowlisting and authorization;
- execution of read-only capabilities;
- side-effect mediation;
- distributed correlation and central observability;
- Home Assistant credentials and capability adapters;
- Memory scope/admission policy.

The Router knows the logical `nyra-llm` service and LLM purpose. It does not
choose provider or model.

### 4.2 `nyra-llm` owns

`nyra-llm` owns:

- prompt construction internal to each typed purpose;
- provider-independent inference;
- provider adapter abstraction;
- provider/model configuration;
- provider/model fallback strategy;
- structured output parsing and validation;
- retry behavior internal to a provider attempt where appropriate;
- ephemeral `reasoning_id` state;
- provider usage metadata;
- LLM-local health/readiness and technical diagnostics.

`nyra-llm` does not own:

- conversation sessions;
- trusted identity resolution;
- clarification persistence;
- Router policy;
- Home Assistant entity resolution;
- Home Assistant credentials;
- Memory authorization/persistence;
- Skills validation;
- side-effect execution.

### 4.3 Provider independence

Provider/model selection is entirely private to `nyra-llm`.

The Router sends:

```text
purpose + typed input + controlled context
```

and never sends:

```text
provider = ...
model = ...
```

M6 defines a Nyra-owned provider interface:

```text
ProviderAdapter
```

and initially implements that interface through a private LiteLLM-backed
adapter.

Conceptually:

```text
Nyra contracts
     |
     v
ProviderAdapter          # Nyra-owned interface
     |
     v
LiteLLMAdapter           # Nyra-owned implementation
     |
     v
LiteLLM                  # replaceable dependency
     |
     v
configured provider/model
```

Router, Skills, Memory, Home Assistant, and shared orchestration code must not
depend on LiteLLM data structures.

LiteLLM is therefore an implementation detail, not an architectural boundary.

## 5. LLM purposes

The shared LLM protocol recognizes three typed purposes:

```text
SEMANTIC
REASONING
MEMORY_EXTRACTION
```

M6 production scope is:

```text
SEMANTIC          -> implemented and operational
REASONING         -> implemented and operational
MEMORY_EXTRACTION -> protocol present, automatic activation out of scope
```

Each purpose has a distinct contract. There is no universal untyped "ask the
LLM" payload.

## 6. `SEMANTIC` contract

`SEMANTIC` provides stateless structured interpretation.

It is suitable for components such as Skills that need semantic interpretation
without global conversational reasoning.

Conceptual flow:

```text
Router / Router-mediated Skills need
       |
       v
nyra-llm : SEMANTIC
       |
       v
SemanticResult
```

`SEMANTIC` is constrained as follows:

- stateless;
- no `reasoning_id`;
- no capability loop;
- no Memory search;
- no Home Assistant access;
- no entity resolution implementation;
- no side effects;
- no conversation ownership;
- output must conform to the shared `SemanticResult` contract.

Any semantic interpretation requested on behalf of Skills must still preserve
the first-level no-lateral-communication rule. Skills does not call
`nyra-llm` directly; the Router mediates the request.

## 7. `REASONING` contract

### 7.1 Request

A reasoning request conceptually contains:

```text
ReasoningRequest
- purpose = REASONING
- request_context
- current_user_input
- conversation_context
- clarification_context?
- capability_results?
- reasoning_id?
```

The concrete protocol should use focused shared models rather than exposing the
entire internal Router state.

The Router constructs all authoritative context before invoking `nyra-llm`.

### 7.2 Closed outcome set

The M6 reasoning protocol has exactly four outcomes:

```text
COMPLETED
NEEDS_CAPABILITY
NEEDS_CLARIFICATION
FAILED
```

Unknown outcome values are contract failures.

### 7.3 `COMPLETED`

A completed response may contain:

```text
response_text
proposed_execution_plan?
```

If a plan is present, it must have:

```text
origin = REASONING_LLM
validation_state = PROPOSED
```

`nyra-llm` cannot return a plan as `VALIDATED`.

### 7.4 `NEEDS_CAPABILITY`

`NEEDS_CAPABILITY` requests exactly one Router-controlled read-only capability
operation for the current reasoning round.

The request is structured and typed; it is not arbitrary prose or an arbitrary
URL/tool call.

### 7.5 `NEEDS_CLARIFICATION`

`NEEDS_CLARIFICATION` contains a user-facing clarification question and a typed
reason where useful.

It does not create LLM-owned conversational state.

The Router persists the pending clarification and decides whether a later user
turn continues it.

### 7.6 `FAILED`

`FAILED` is a terminal reasoning result after any eligible internal technical
fallbacks have been exhausted, or a valid semantic inability to complete the
request has been reached.

Technical transport/provider failures and semantic reasoning failures must
remain distinguishable in the protocol/diagnostics.

## 8. Strict Skills-to-LLM routing

The only automatic entry into global reasoning is a true `MISS` returned by the
Skills CHECK phase.

The routing rule is:

```text
Skills CHECK
├─ HANDLED              -> deterministic Skills path only
├─ NEEDS_CLARIFICATION  -> Router-owned clarification
├─ FAILED               -> terminal Skills failure
└─ MISS                 -> REASONING may begin
```

Once Skills returns `HANDLED`, an execute-time `MISS` or execute-time error must
not silently fall through to the LLM.

If a handled deterministic execution fails, that failure remains in the
deterministic path.

Technical retries for deterministic execution, if supported, are independent
from semantic fallback and do not change this rule.

This strict boundary must be covered by permanent regression tests because the
pre-M6 lifecycle contains a transitional path capable of turning an
execute-stage `MISS` into LLM fallback.

## 9. Reasoning context

### 9.1 Least-context projection

The Router must not automatically send the complete `RequestContext`.

It constructs a typed, minimized reasoning projection containing only what the
purpose requires.

Conceptually:

```text
ReasoningContext
- language
- trusted_identity_subset
- policy_subset
- source / area when relevant
- current_user_input
- bounded_conversation_history
- clarification_context?
- required operational_context_subset?
```

### 9.2 Language

The request language remains authoritative.

All user-facing generated text must follow the language carried by the request
contract.

The assistant's spoken/written identity must not hardcode the wake word or the
name "Nyra"; wake word and assistant phrasing remain independent.

### 9.3 Trusted identity

The LLM receives only the minimized trusted identity fields required for the
reasoning task.

Biometric details, Speaker-ID internals, confidence traces, raw audio, and other
identity provenance are not part of ordinary LLM context unless a future,
explicitly authorized contract requires them.

The model never determines trusted identity.

### 9.4 Conversation history

Conversation history is Router-owned.

The Router passes a deterministic bounded window rather than the complete
session transcript or an unbounded provider context.

The window must have configurable limits and a stable selection rule.

Conversation history represents current-session continuity. It is not a
replacement for Semantic Memory.

### 9.5 Context categories remain distinct

M6 preserves these meanings:

```text
Conversation history
= continuity of the active conversation

Semantic Memory
= persistent knowledge across conversations

Operational Context
= deterministic current facts/context

Trusted identity/policy
= Router-authoritative security context
```

These categories must not be collapsed into one opaque prompt history.

## 10. Semantic Memory during reasoning

M6 does not automatically pre-enrich every Skills MISS with Semantic Memory.

Semantic Memory is available through a Router-mediated read-only reasoning
capability:

```text
SEARCH_MEMORY
```

Conceptual flow:

```text
nyra-llm
   |
   | NEEDS_CAPABILITY(SEARCH_MEMORY)
   v
Router
   |
   | identity + scope + policy
   v
Memory
   |
   v
Router
   |
   | structured result, same reasoning_id
   v
nyra-llm
```

`nyra-llm` does not communicate directly with `nyra-memory`.

The Router determines allowed Memory scope based on trusted identity and Memory
policy. The LLM cannot expand its own authorization.

`SEARCH_MEMORY` results are advisory input to reasoning. They do not become
automatic persistent context or mutate Memory.

## 11. Read-only capability loop

### 11.1 Initial M6 allowlist

M6 implements these read-only reasoning capabilities:

```text
SEARCH_MEMORY
READ_STATE
READ_ATTRIBUTE
DISCOVER_RESOURCES
```

The configured environment allowlist may restrict this set further.

Configuration cannot dynamically invent new capability types. A capability must
be implemented and typed in Nyra code before it can be enabled.

### 11.2 Capability request

A capability request is structured:

```text
CapabilityRequest
- capability
- parameters
- functional_reason?
```

`functional_reason`, if present, is a brief operational justification. It is not
chain-of-thought and must not be used to solicit or persist hidden reasoning.

### 11.3 Capability result

A capability returns a structured result:

```text
CapabilityResult
- capability_call_id
- capability
- status
- data?
- error?
```

A normal capability failure such as "resource not found" may be returned to the
same reasoning loop so the model can adapt.

### 11.4 Capability ownership

The Router performs:

- capability type validation;
- parameter validation;
- policy validation;
- trusted identity checks;
- budget/timeout enforcement;
- target/resource mediation;
- actual capability execution;
- correlation.

The LLM service only requests.

### 11.5 `READ_STATE`

`READ_STATE` returns the current normalized state of an authorized resource.

It must not expose unnecessary Home Assistant internals.

### 11.6 `READ_ATTRIBUTE`

`READ_ATTRIBUTE` returns one authorized attribute or a small explicitly
requested attribute set from a resource.

It must not act as an unrestricted entity dump.

### 11.7 `DISCOVER_RESOURCES`

`DISCOVER_RESOURCES` performs controlled discovery through Router-owned resource
resolution/discovery facilities.

It returns a reduced, typed representation sufficient for reasoning.

It is not permission to enumerate arbitrary Home Assistant data or to access
Home Assistant directly.

### 11.8 Forbidden capability requests

The reasoning capability loop must reject, at minimum, requests equivalent to:

```text
TURN_ON
TURN_OFF
OPEN
CLOSE
SET_*
CALL_SERVICE
HTTP_REQUEST
WRITE_MEMORY
DELETE_MEMORY
CREATE_AUTOMATION
UPDATE_AUTOMATION
```

A side-effect request made as a reasoning capability is a contract/policy
violation, not an action to execute.

## 12. Reasoning budget and timeout

The Router owns both:

- maximum capability round trips per reasoning;
- total end-to-end reasoning timeout.

The initial default maximum is:

```text
3 capability round trips
```

The value is configurable.

The total timeout is configurable and must be selected during implementation
using realistic provider and capability latency evidence rather than an
arbitrary design-time constant.

The timeout includes provider inference and Router capability round trips for
the reasoning operation.

Exceeding capability budget terminates the loop with a typed
`BUDGET_EXCEEDED` failure.

Exceeding the total timeout terminates the loop with a typed `TIMEOUT` failure.

`nyra-llm` cannot override these Router limits.

## 13. Ephemeral reasoning state

`nyra-llm` may maintain ephemeral state identified by:

```text
reasoning_id
```

A reasoning ID:

- belongs to one reasoning operation only;
- is bound to one `trace_id`;
- is not a conversation/session identifier;
- cannot migrate to another trace;
- expires on completion, failure, timeout, or budget exhaustion;
- must be rejected on trace mismatch or invalid continuation.

The Router remains the owner of conversation/session state.

Reasoning state should contain only what is required to continue the bounded
capability loop.

## 14. Clarification ownership

An LLM can request clarification, but it cannot own the clarification lifecycle.

Flow:

```text
LLM -> NEEDS_CLARIFICATION
          |
          v
        Router
          |
          +--> persist pending clarification
          +--> present localized question

later user turn
          |
          v
        Router
          |
          +--> validate pending clarification
          +--> rebuild controlled context
          +--> continue/restart reasoning as defined by lifecycle
```

Clarification expiry is configurable and Router-owned.

If the clarification has expired, a later utterance is treated according to the
normal Router lifecycle rather than an indefinite LLM session.

## 15. LLM-proposed actions and the Skills action gate

Side effects never use the read-only capability loop.

If reasoning concludes that an action is appropriate, it may return:

```text
COMPLETED
+ proposed_execution_plan
```

The plan must be:

```text
origin = REASONING_LLM
validation_state = PROPOSED
```

The required path is:

```text
nyra-llm
   |
   | proposed ExecutionPlan
   v
Router
   |
   v
LlmActionGate
   |
   v
Skills validation/materialization
   |
   v
Router-owned capability
   |
   v
optional Home Assistant
```

Skills remains the mandatory action validator/materializer.

The Router remains the capability executor.

M6 must close the existing scaffold gap and expose/wire the focused Skills plan
validation/materialization contract required by this flow. It must not introduce
a second action execution path.

Any rejection by Skills remains a rejection. The LLM cannot bypass or override
it.

## 16. Provider adapter and LiteLLM

### 16.1 Nyra-owned abstraction

M6 defines an internal provider abstraction that covers only Nyra's required
inference semantics.

The abstraction must normalize:

- typed inference request;
- structured response;
- provider errors;
- timeout/rate-limit/unavailable classes;
- structured-output contract errors;
- usage metadata;
- provider/model identifiers for diagnostics only.

Provider-specific SDK objects must not escape the adapter layer.

### 16.2 LiteLLM implementation

The initial adapter uses LiteLLM as a library/private implementation detail.

M6 does not introduce a separately deployed LiteLLM proxy unless implementation
evidence demonstrates that a separate service is required and the architecture
is re-approved.

### 16.3 Configuration

`nyra-llm` configuration owns:

- primary provider/model route;
- fallback provider/model route(s);
- provider credentials;
- provider-specific transport configuration;
- optional pricing metadata;
- provider-level timeouts/retry values where distinct from Router total timeout.

Credentials must come from deployment configuration/secrets and must not be
committed to Git.

Router configuration contains the `nyra-llm` service endpoint and Router-owned
reasoning limits, but no provider API keys and no provider/model selection.

## 17. Provider/model fallback

Fallback is allowed only for technical or contract failures.

Eligible examples include:

- connection failure;
- provider service unavailable;
- provider 5xx class failure;
- provider timeout;
- rate limiting where configured policy permits fallback;
- malformed response;
- structured output that cannot satisfy the expected contract after the allowed
  validation/retry policy.

Fallback must not occur because:

- the model's valid answer appears weak;
- confidence is low;
- another model might provide a "better" answer;
- the caller dislikes a semantically valid result.

Conceptual flow:

```text
primary route
   |
   +-- valid result ----------------------> return
   |
   +-- technical/contract failure
                |
                v
          fallback route
                |
                +-- valid result ---------> return
                |
                +-- exhausted -----------> technical FAILED
```

Fallback policy is configured inside `nyra-llm`.

Router observes the normalized outcome and technical diagnostics but does not
select the route.

## 18. Buffered responses and future streaming

M6 returns complete buffered responses.

Conceptually:

```text
provider generates complete response
        |
        v
nyra-llm validates/normalizes
        |
        v
Router receives complete typed result
```

End-to-end provider token streaming through Router, TTS, and speaker is outside
M6.

However:

- protocol ownership must not assume that provider/model state lives in Router;
- reasoning correlation must be stable;
- action/capability safety must remain independent of transport;
- no design choice should require replacing the trust boundaries to add
  streaming later.

Streaming, if implemented later, must preserve the same capability and action
security rules.

## 19. Error model

M6 distinguishes at least three error classes.

### 19.1 Provider/transport failure

Examples:

- connection failure;
- timeout;
- 5xx;
- eligible rate limit;
- malformed provider output;
- structured output contract failure.

These errors may trigger internal provider/model fallback.

### 19.2 Reasoning failure

Examples:

- a valid `FAILED` reasoning outcome;
- inability to complete a request with available information;
- a valid terminal reasoning condition.

These do not trigger provider fallback merely because the result is
unsatisfactory.

### 19.3 Policy/security failure

Examples:

- forbidden capability;
- invalid capability parameters;
- authorization violation;
- capability budget exceeded;
- Router total timeout exceeded;
- `reasoning_id` / `trace_id` mismatch;
- invalid proposed execution origin/state.

Policy/security failures terminate or reject the affected flow according to the
typed lifecycle. They are never recovered by giving the LLM more authority.

## 20. Privacy

M6 follows least-context and least-persistence principles.

Normal technical logs must not persist:

- full prompts;
- full conversation history;
- `SEARCH_MEMORY` content;
- chain-of-thought;
- provider credentials;
- Home Assistant credentials;
- raw Home Assistant payload dumps unless explicitly sanitized and needed for a
  technical diagnostic contract.

No chain-of-thought is requested, exposed, or persisted.

If a future debug mode captures user text or model output, it requires an
explicit design and must be disabled by default, bounded, and clearly surfaced
as sensitive diagnostics.

Provider-bound identity data must be minimized to fields required by the
reasoning task.

## 21. Observability and correlation

Each LLM request and reasoning loop must preserve distributed correlation.

At minimum, diagnostics should support:

```text
trace_id
request_id
reasoning_id
attempt_id
capability_call_id
```

where applicable.

Per-inference technical diagnostics should include:

- purpose;
- normalized outcome;
- provider actually used;
- model actually used;
- attempt number;
- fallback used yes/no;
- latency;
- input token count when available;
- output token count when available;
- structured-output validity;
- capability count;
- capability types;
- terminal error category/code where applicable.

These diagnostics do not make provider/model a Router selection concern.
Provider/model values are observational metadata.

### 21.1 Cost accounting

M6 records an optional estimated cost when pricing information is configured and
the provider reports sufficient usage.

If pricing cannot be determined:

```text
cost_estimate = null
```

Token counts remain available independently.

Pricing is configuration/diagnostic data, not routing authority.

## 22. Nyra Admin

M6 extends Nyra Admin with Router-backed LLM diagnostics.

Admin must not become a second orchestration path or connect directly to
providers.

The initial diagnostics should expose enough information to answer:

- is `nyra-llm` configured and ready?
- which logical purposes are operational?
- did a reasoning request complete, clarify, request capabilities, or fail?
- which provider/model was actually used?
- was fallback used?
- what was the latency?
- how many input/output tokens were reported?
- what optional estimated cost was recorded?
- which read-only capability types were invoked?
- what technical/policy error category occurred?

Sensitive prompt, Memory content, and chain-of-thought are not displayed by
default because they are not persisted by the normal observability contract.

## 23. Health and readiness

`nyra-llm` exposes:

```text
GET /health
GET /ready
```

`/health` reports process/service liveness.

`/ready` verifies configuration required to accept the enabled purposes without
performing an unnecessary paid inference on every readiness probe.

Readiness must fail when required provider configuration is structurally
invalid.

Provider outages should be represented in operational diagnostics according to
the chosen readiness policy without turning health probes into uncontrolled
provider traffic.

Router service diagnostics must include `nyra-llm` readiness.

## 24. Security invariants

M6 must permanently test these invariants:

1. only Skills CHECK `MISS` enters global reasoning automatically;
2. `HANDLED`, `NEEDS_CLARIFICATION`, and `FAILED` never auto-fallback to LLM;
3. execute-stage deterministic failure/MISS never auto-falls through to LLM;
4. `nyra-llm` cannot call Home Assistant directly;
5. `nyra-llm` cannot call Memory directly;
6. reasoning capabilities are read-only and allowlisted;
7. unknown/side-effect capability requests are rejected;
8. Router applies identity and policy before capability execution;
9. reasoning budget and timeout are Router-owned;
10. reasoning IDs cannot cross traces;
11. LLM-proposed plans are always `REASONING_LLM` + `PROPOSED`;
12. proposed action plans always pass through Skills validation/materialization;
13. Skills rejection cannot be overridden by the LLM;
14. Router/Skills never need provider API keys;
15. Router/Skills do not choose provider/model;
16. fallback occurs only on eligible technical/contract failures;
17. normal logs do not contain chain-of-thought or persisted Memory payloads.

## 25. TDD strategy

M6 implementation follows strict test-driven development.

For each functional slice:

1. define expected behavior;
2. add the permanent test first;
3. run the focused test and demonstrate RED for the intended missing behavior;
4. add the minimum implementation;
5. rerun the focused test to GREEN;
6. run related regression tests;
7. run the broader/full suite when appropriate;
8. run `git diff --check`;
9. review changed-file scope and diff;
10. create a focused commit;
11. push the dedicated M6 branch.

For defects discovered during M6:

```text
root-cause analysis
 -> permanent RED reproducer
 -> minimal fix
 -> focused GREEN
 -> regression
```

No speculative production patch is considered complete.

## 26. Minimum permanent test areas

The implementation plan must include permanent coverage for at least:

- LLM purpose/request/result protocol validation;
- `SEMANTIC` stateless structured output;
- `REASONING` four-outcome contract;
- provider adapter normalization;
- LiteLLM implementation isolation;
- technical-only fallback;
- no semantic-quality fallback;
- strict Skills CHECK `MISS` routing;
- prevention of execute-stage LLM fallback;
- Router LLM client and timeout handling;
- bounded conversation context;
- language propagation;
- minimized trusted identity propagation;
- Router-owned clarification continuation/expiry;
- ephemeral reasoning ID / trace binding;
- capability allowlist;
- capability parameter validation;
- three-round default budget;
- budget exhaustion;
- total timeout enforcement;
- `SEARCH_MEMORY` scope/policy mediation;
- `READ_STATE`;
- `READ_ATTRIBUTE`;
- `DISCOVER_RESOURCES`;
- rejection of side-effect capability requests;
- normal capability error returned to reasoning;
- LLM action proposal origin/state validation;
- Skills validation/materialization action gate;
- Router-owned side-effect capability execution;
- usage/token/fallback diagnostics;
- privacy-safe logging;
- health/readiness;
- Admin diagnostics;
- end-to-end Skills MISS -> LLM response;
- end-to-end capability round trip;
- end-to-end LLM proposal -> Skills gate -> Router capability.

## 27. Deployment architecture

M6 introduces `nyra-llm` as a dedicated Nyra service in the existing production
environment.

Deployment must follow repository conventions used by current first-level
services and remain reproducible from Git-controlled assets.

Production changes are prohibited during normal development.

Before production deployment:

1. implementation branch and required suite must be green;
2. exact production changes must be presented;
3. backup must be created;
4. rollback procedure must be demonstrated/reviewed;
5. explicit user authorization is required.

Provider credentials are installed only through protected deployment
configuration and never committed.

## 28. Production verification

After authorized deployment, M6 is not considered complete until real
verification covers, as applicable:

- `nyra-llm` health;
- `nyra-llm` readiness;
- Router recognition of LLM service readiness;
- a real `SEMANTIC` request;
- a real Skills CHECK `MISS` reaching `REASONING`;
- a buffered text response;
- a real read-only capability round trip;
- `SEARCH_MEMORY` through Router policy;
- Home Assistant state/resource read through Router capability;
- an LLM clarification path with Router-owned pending state;
- an LLM-proposed action forced through Skills validation/materialization;
- rejection of a forbidden side-effect capability request;
- a controlled technical fallback test where safely possible;
- trace/request/reasoning/capability correlation;
- token/latency/fallback diagnostics;
- restart/recovery behavior where relevant;
- Nyra Admin LLM diagnostics;
- physical speaker/Home Assistant request verification where applicable.

Production verification must prove the trust boundaries, not only HTTP 200
responses.

## 29. Rollback

Deployment assets must define a rollback that restores the prior Router/Skills
production behavior without requiring ad-hoc edits.

Rollback must cover:

- Router configuration/code change;
- `nyra-llm` service installation/update;
- shared protocol compatibility;
- Admin changes;
- provider configuration;
- any Skills plan-gate endpoint added by M6.

Rollback must not require deleting user Memory or identity data.

## 30. Explicitly out of scope

M6 does not include:

- end-to-end token streaming;
- streaming TTS/speaker response;
- automatic persistent Memory extraction from ordinary conversation;
- LLM-owned conversation sessions;
- LLM-owned clarification persistence;
- direct LLM -> Home Assistant access;
- direct LLM -> Memory access;
- direct LLM -> Skills access;
- arbitrary HTTP/browser/tool execution by the LLM;
- side-effect reasoning capabilities;
- provider/model selection in Router or Skills;
- a separately deployed LiteLLM proxy by default;
- fallback based on subjective response quality;
- chain-of-thought capture or display;
- redesign of Speaker-ID;
- unrelated Home Assistant or Skills feature expansion.

## 31. Completion criteria

M6 is complete only when all of the following are true:

- this design/spec has been approved;
- the implementation plan has been approved;
- all implementation slices followed permanent-test-first TDD;
- focused and regression tests are green;
- the full repository suite is green;
- `git diff --check` is clean;
- the M6 branch scope has been reviewed;
- the branch is clean and pushed;
- production deployment has been explicitly authorized;
- production backup and rollback are verified;
- production health/readiness is verified;
- end-to-end reasoning is verified;
- capability loop is verified;
- action-gate path is verified;
- observability/privacy boundaries are verified;
- relevant physical speaker/Home Assistant validation is complete;
- `docs/state/CURRENT_STATE.md` is updated;
- `ROADMAP.md` is updated;
- `README.md` and other affected documentation are updated;
- final documentation is committed and pushed;
- user explicitly authorizes final merge;
- merge to `main` is completed;
- `main` and `origin/main` are verified identical.

Until the final merge authorization, M6 remains on its dedicated branch.

## 32. Approved design decisions summary

The M6 design freezes these decisions:

1. `nyra-llm` is a dedicated first-level specialist service.
2. `nyra-llm` owns provider/model selection and technical fallback.
3. Router and Skills never choose or need to know provider/model names.
4. Nyra owns `ProviderAdapter`; LiteLLM is the initial private implementation.
5. `SEMANTIC` and `REASONING` are operational in M6.
6. `MEMORY_EXTRACTION` remains protocol-visible but automatic activation is out
   of scope.
7. only Skills CHECK `MISS` can automatically enter global reasoning.
8. execute-stage deterministic failures do not fall through to LLM.
9. conversation history is Router-owned and bounded.
10. Semantic Memory is requested through `SEARCH_MEMORY`, not automatically
    injected into every reasoning prompt.
11. the M6 reasoning loop implements read-only capabilities.
12. initial capabilities are `SEARCH_MEMORY`, `READ_STATE`, `READ_ATTRIBUTE`,
    and `DISCOVER_RESOURCES`.
13. the capability allowlist may be restricted by configuration but not expanded
    beyond implemented typed capabilities.
14. Router owns capability authorization, round-trip budget, and total timeout.
15. the default capability round-trip budget is three.
16. reasoning outcomes are exactly `COMPLETED`, `NEEDS_CAPABILITY`,
    `NEEDS_CLARIFICATION`, and `FAILED`.
17. clarification state remains Router-owned.
18. side effects are proposed only as `REASONING_LLM` / `PROPOSED`
    `ExecutionPlan` objects.
19. all proposed side effects pass through Skills validation/materialization and
    Router-owned capability execution.
20. provider/model fallback occurs only for eligible technical/contract failures.
21. M6 responses are buffered.
22. normal diagnostics store technical metadata but not full prompts, Semantic
    Memory payloads, or chain-of-thought.
23. token usage is recorded when available.
24. cost estimation is optional and nullable when pricing is unavailable.
25. Nyra Admin surfaces Router-backed LLM diagnostics without becoming an
    orchestration or provider boundary.
