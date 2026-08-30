# Nyra Architecture

## Overview

Nyra is built around a centralized Router acting as the trusted orchestration, context, policy, capability, and observability boundary of the platform.

First-level Nyra services communicate only with the Router.

```text
                         +------------------+
                         |  Home Assistant  |
                         +---------^--------+
                                   |
                         +---------+--------+
                         |    NYRA ROUTER    |
                         | orchestration    |
                         | identity         |
                         | sessions         |
                         | context          |
                         | policies         |
                         | capabilities     |
                         | observability    |
                         +--+----+----+----+
                            |    |    |    |
                         Skills Memory Voice LLM
                                |
                           Embeddings
                     private Memory dependency
```

## Communication model

First-level services know only the Router.

```text
Home Assistant -> Router
Skills -> Router
Memory -> Router
Voice -> Router
LLM -> Router

Router -> Home Assistant
Router -> Skills
Router -> Memory
Router -> Voice
Router -> LLM
```

Private implementation dependencies may communicate directly. Example: `Memory -> Embeddings`.

## Router responsibilities

The Router owns request and session lifecycle, source information, identity, area context, operational context resolution, semantic memory enrichment, routing, service registry, capability authorization, security policies, final response coordination, centralized logging, distributed tracing, observability, and the single Nyra administration UI.

## Context model

Every request receives a trusted context created and owned by Router.

### Request context
- request identifier
- session identifier
- source
- identity when available
- area
- language
- timestamp

### Session context
Conversation and follow-up information associated with the active session.

### Operational context
Operational context is resolved for every request. Examples include entity aliases, user-defined names, mappings, shortcuts, and deterministic preferences required to interpret a request. It must be fast and deterministic.

### Semantic long-term memory
Semantic memory is retrieved only when relevant. Downstream services do not directly access Memory; additional memory must be requested through a Router capability.

## Capability model

Protected resources are accessed through Router capabilities, for example `Skills -> Router -> Home Assistant` and `LLM -> Router -> Memory`.

## Administration and observability

Router exposes the only Nyra administration interface. Service-specific user interfaces exposed by Memory, Skills, Voice, or other first-level components are temporary and will be removed as services are migrated to Nyra v1. Router obtains service-specific information through service APIs and presents it through dedicated pages in the centralized Nyra Control Center.
