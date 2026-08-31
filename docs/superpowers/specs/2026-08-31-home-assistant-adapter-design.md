# Home Assistant Adapter — Milestone 2 Design

**Status:** Approved in design discussion; pending repository review  
**Date:** 2026-08-31  
**Milestone:** 2 — Home Assistant Adapter  
**Depends on:** `docs/superpowers/specs/2026-08-31-component-contract-v1-design.md`

## 1. Purpose

Milestone 2 introduces the definitive thin Home Assistant adapter for Nyra. Home Assistant is an ingress/egress boundary, not a second orchestrator. It collects authoritative HA context, creates/preserves ingress correlation IDs, forwards requests to `nyra-router`, converts responses to Home Assistant conversation results, and bridges real-time pipeline state to the originating speaker.

There is no legacy/parallel Nyra path in this milestone.

## 2. Architecture

```text
Speaker / HA Assist
        |
        v
custom_components/nyra
        |
        | POST /v1/requests
        v
    nyra-router
        |
        v
custom_components/nyra
        |
        v
HA ConversationResult / TTS
```

Real-time state is a separate path:

```text
nyra-router -> semantic pipeline events -> HA Nyra bridge -> originating ESPHome speaker -> LED/audio feedback
```

Router publishes semantic state, never RGB values or ESPHome-specific commands.

## 3. Adapter Responsibilities

The adapter SHALL register Nyra as a Home Assistant conversation agent; accept Assist input; collect only authoritative HA metadata; generate/preserve `session_id` and `request_id`; call `POST /v1/requests`; map Router output to `ConversationResult`; maintain runtime conversation/session/request mapping; route correlated real-time pipeline events to the correct speaker; translate semantic speaker states into visual/audio behavior; and support setup/unload/reload/readiness/controlled failures.

It SHALL NOT perform semantic interpretation, entity resolution, Skills/LLM selection, Memory behavior, identity inference, alternate Assist fallback, blind conversational retry, Router lifecycle duplication, or expose Router internals as LED states.

## 4. Correlation Ownership

HA adapter generates `session_id = ses_<UUIDv4>` and `request_id = req_<UUIDv4>`. Router generates `trace_id = trc_<UUIDv4>` per execution/turn.

A new intent in the same session uses the same session, a new request and a new trace. A clarification/follow-up continuation uses the same session and request, with a new trace.

The HA conversation -> Nyra session mapping is runtime-only and expires. Persistent Nyra memory must not depend on it.

## 5. Ingress Types and Metadata

Use `ha_assist` when HA has an authenticated/trusted HA user identity. Use `ha_speaker` for physical speaker/satellite input where personal identity must be resolved by Nyra.

For `ha_speaker`, device ownership, room, speaker name or prior usage SHALL NOT be treated as personal identity. Source and identity are separate.

Forward only values HA actually knows, including language, source/device/satellite, HA area, conversation context, and authenticated HA user identity when applicable. Do not infer area from natural language.

## 6. Wire Contract

Use the existing Router endpoint:

```http
POST /v1/requests
```

No HA-specific duplicate execution endpoint is introduced. Exact implementation field names follow the current `shared/protocol` models and Router API, not illustrative duplicate DTOs.

A clarification response preserves the active `request_id`. A terminal response closes it; the next intent gets a new one.

## 7. Integration Structure

Intended responsibilities:

```text
homeassistant/custom_components/nyra/
├── __init__.py       # config entry lifecycle/runtime
├── manifest.json
├── config_flow.py    # minimal UI config + Router validation
├── const.py
├── client.py         # Router HTTP client
├── conversation.py   # HA conversation boundary
├── session.py        # runtime conversation/session/request mapping
└── speaker.py        # semantic state -> target speaker feedback
```

Physical layout may adapt to current HA APIs while preserving these boundaries.

## 8. Configuration and Readiness

Configure via HA config entry/UI. Minimum configuration: Router base URL and existing ingress token when required. Adapter owns a reasonable HTTP timeout.

Validate Router using `/ready`; `/health` retains process-alive semantics.

Do not add mTLS, service identity or a new service-to-service authentication scheme in v1.

## 9. Failure Policy

Connection failure/timeout -> controlled Nyra-unavailable result. Router 4xx -> contract/request failure, no fallback. Router 5xx -> unavailable/failure, no automatic conversational retry. Invalid Router payload -> adapter failure, no fallback.

No blind retry is allowed because a timed-out request may already have executed a non-idempotent operation.

## 10. Speaker Semantic States

Pipeline state and rendering are separate. Core grammar:

```text
Nyra listening -> fast pulsing white
Nyra speaking  -> audio-reactive purple
```

| Semantic state/event | Speaker rendering |
| --- | --- |
| `IDLE` | LEDs off |
| `LISTENING` | white, fast pulse |
| `TRANSCRIBING` | white, fast pulse |
| `IDENTIFYING` | warm-white comet |
| identity recognized | exactly 2 fast green blinks |
| identity not recognized | exactly 2 fast red blinks |
| identity changed from previous speaker in active session | exactly 2 fast blue blinks |
| `PROCESSING_LOCAL` | turquoise comet |
| `PROCESSING_GLOBAL` | rainbow comet |
| `USING_TOOL` | yellow comet |
| `WAITING_CLARIFICATION` | same rendering as `LISTENING` |
| `SPEAKING` | purple, brightness modulated by TTS/audio activity |
| terminal `ERROR` when normal speech cannot be delivered | red error feedback |
| session close | closing sound + blue blink -> `IDLE` |

`UNDERSTANDING`, `EXECUTING`, and `SUCCESS` are not separate speaker visual states in v1. Internal Memory/Skill/LLM/tool implementation details remain observability data.

`USING_TOOL` is temporary and restores the surrounding processing visual, e.g. `PROCESSING_GLOBAL -> USING_TOOL -> PROCESSING_GLOBAL`.

There is no general speaker `WAITING` state. Deferred delays/waits belong to Jobs/Behaviors and must not leave the speaker illuminated.

## 11. Identity Feedback

`IDENTIFYING` is a pipeline phase; the identity result is a transient feedback event. After identification, exactly two fast blinks occur: green for recognized, red for not recognized, blue for recognized but different from the previously identified speaker in the same active session.

Milestone 2 defines transport/rendering, not biometric identity implementation.

## 12. Session Opening

Wake-word recognition occurs locally at the speaker/satellite boundary.

```text
WAKE_WORD_DETECTED
-> mandatory local activation/opening sound
-> open/activate conversational session
-> LISTENING
-> fast pulsing white
```

The opening sound must not wait for a Router round trip. It means: Nyra heard the wake word and the user may speak.

## 13. Session Closing

Router normally owns the decision that an active conversational session is finished. Terminal causes include: final action/response needs no more input; user semantically ends the conversation; clarification/follow-up timeout; explicit cancellation/interruption; terminal error.

```text
SESSION_CLOSED
-> closing sound
-> blue blink
-> IDLE
```

Close feedback is lifecycle feedback, not `SUCCESS`.

## 14. Speaking Outside User-Initiated Sessions

`SPEAKING` is a device output state, not proof of a listening session. A Job/Behavior that needs to speak uses the same purple audio-reactive `SPEAKING` behavior without fake wake word, `SESSION_OPENED`, or `LISTENING`.

## 15. Event Correlation and Routing

Real-time events carry enough correlation/routing data to reach only the owning speaker, including applicable `session_id`, `request_id`, `trace_id`, source/device/speaker ID, semantic state/event, and timestamp. Central Router state may enrich distributed child events with authoritative session/source routing. `origin_request_id` remains available per Component Contract v1.

Concurrent speakers must never cross-render each other's state.

## 16. Real-Time Requirement

Speaker-state feedback is part of the live interaction contract, not merely observability. Events are emitted on transition and delivered without waiting for request completion. Persistence/logging must not be the mechanism used for live speaker state.

## 17. HA Conversation Lifecycle

Conceptually:

```text
HA conversation
  +-- Nyra session_id
  +-- active request_id only while continuation is required
```

Terminal request clears active request. Clarification/follow-up preserves it. New intent allocates a new request. Session mappings expire.

## 18. Testing Requirements

Tests cover: session creation/reuse/expiration; request creation/preservation; new Router trace per turn; `ha_assist` trusted identity; `ha_speaker` without invented identity; source/device/area/language propagation; actual `/v1/requests` contract; `ConversationResult` mapping; timeout/unavailable/invalid payload; no blind retry; no legacy fallback; config-entry lifecycle; `/ready`; correct speaker routing under concurrency; all visual mappings; tool-state restoration; wake opening sound before listening; close sound + blue blink; Job speech without listening lifecycle; no visual waiting for deferred Jobs; and authoritative Router `RequestContext`.

Hardware-specific rendering SHALL be behind a narrow output interface so semantic behavior is testable without physical hardware.

## 19. Acceptance Criteria

A definitive end-to-end speaker interaction must demonstrate:

```text
wake word
-> local activation sound
-> LISTENING / white fast pulse
-> speech ingress
-> IDENTIFYING / warm-white comet
-> identity result blink
-> PROCESSING_LOCAL or PROCESSING_GLOBAL
-> optional USING_TOOL
-> SPEAKING / purple audio-reactive output
-> Router determines session terminal
-> closing sound + blue blink
-> IDLE
```

Correlation must be observable through Router/Control Center.

New intent: same session, new request, new trace. Clarification/follow-up: same session, same request, new trace. Concurrent speakers remain independently routed. Deferred Jobs do not keep a speaker waiting. Job speech uses `SPEAKING` without fabricating a wake/listening lifecycle.

## 20. Out of Scope

Milestone 2 does not implement biometric Speaker-ID, Memory migration, Skills migration, reasoning LLM migration, general Capability migration beyond current Router needs, mTLS/service identity, legacy/parallel HA routing, persistent conversational state in HA, or LED-specific logic in Router.

## 21. Design Invariants

1. HA remains a thin adapter; Router remains central orchestrator.
2. HA owns ingress session/request IDs; Router owns per-execution trace ID.
3. Source/device never implies personal identity.
4. No legacy/fallback intelligence path exists in HA.
5. Router publishes semantic state; speaker boundary owns rendering.
6. Listening is fast pulsing white.
7. Speaking is audio-reactive purple, including Job speech.
8. Wake-word success produces a local opening sound before listening.
9. Session closure produces closing sound + blue blink before idle.
10. Local processing is turquoise comet.
11. Global processing is rainbow comet.
12. Tool activity is yellow comet.
13. Identification is warm-white comet followed by exactly two result blinks.
14. General background waiting is not a speaker state.
15. Clarification is semantically distinct but renders as listening.
16. Live speaker state must not depend on observability persistence.
17. Correlated routing prevents concurrent speakers from affecting one another.
