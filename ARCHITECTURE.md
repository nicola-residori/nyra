# Nyra Architecture

## Overview

Nyra is built around a centralized Router acting as the trusted orchestration, context, policy, capability, and observability boundary. First-level Nyra services communicate only with Router.

```text
ESPHome speaker -> Home Assistant -> NYRA ROUTER
                      ^              |
                      +-- events ----+
                      +-- response --+
                      |
                  Assist / TTS / speaker

NYRA ROUTER -> Skills
            -> Memory -> Embeddings (private dependency)
            -> Voice
            -> LLM
```

## Communication model

First-level services know only Router. Private implementation dependencies may communicate directly; for example `Memory -> Embeddings`.

## Home Assistant adapter

Home Assistant is Nyra's first automation-platform adapter. It is deliberately thin: it translates platform-specific conversation and speaker information into the Router contract and translates Router results/events back into Home Assistant and ESPHome behavior. Router remains authoritative for request lifecycle, traces, semantic interaction state, identity outcomes, policies, and protected capabilities.

Speaker source and human identity are separate concepts. An ESPHome speaker supplies a stable `source_id`; a speaker source alone never implies a personal identity. Authenticated Home Assistant Assist requests may carry trusted Home Assistant user context.

```text
INPUT:           ESPHome speaker / Assist -> HA adapter -> Router
OUTPUT:          Router -> HA adapter -> Assist / TTS
REAL-TIME STATE: Router -> event stream -> HA bridge -> ESPHome speaker -> status ring
```

## Speaker interaction contract

Nyra speakers expose a stable, read-only `Nyra Source ID` used to join Router `source_id` values to the correct Home Assistant/ESPHome device.

During an active interaction the Router semantic state drives the status ring. Immediate local hardware lifecycle has this precedence:

1. terminal/error fallback when semantic state is unavailable
2. active TTS announcement playback
3. transient identity feedback
4. current Router semantic interaction state
5. idle/base-device behavior

Identity feedback is an atomic two-blink transient and cannot be truncated by TTS painting. Actual announcement playback owns SPEAKING; TTS generation alone does not.

The interaction vocabulary includes `IDLE`, `LISTENING`, `TRANSCRIBING`, `IDENTIFYING`, `PROCESSING_LOCAL`, `PROCESSING_GLOBAL`, `USING_TOOL`, `WAITING_CLARIFICATION`, `SPEAKING`, and `ERROR`.

Nyra speakers may use local ESPHome micro-wake-word models. Reusable model assets belong in the repository; installation-specific speaker names, addresses, credentials, and room inventory do not.

## Router responsibilities

Router owns request/session lifecycle, source information, identity, area context, operational context, semantic memory enrichment, routing, service registry, capability authorization, security policies, final response coordination, centralized logging, distributed tracing, observability, and the single Nyra administration UI.

## Context model

Every request receives trusted context created and owned by Router: request/session identifiers, source, identity when available, area, language, and timestamp. Operational context is deterministic and always available; semantic long-term memory is conditional and accessed through Router capabilities.

## Component Contract v1 foundation

Shared protocol contracts define correlation, service status, trusted `RequestContext`, semantic understanding, execution plans, platform-neutral behaviors, and typed capability primitives. Child components do not own authoritative session context. Router reconstructs session correlation centrally. Service-to-service authentication is intentionally outside Component Contract v1; the v1 trust boundary is the documented trusted private network.

## Capability model

Protected resources are accessed through Router capabilities, for example `Skills -> Router -> Home Assistant` and `LLM -> Router -> Memory`.

## Administration and observability

Router exposes the only Nyra administration interface. Temporary service-specific UIs are removed as services migrate to Nyra v1.
