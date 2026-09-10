<p align="center">
  <img src="assets/branding/nyra-banner.png" alt="N.Y.R.A. — Neural sYstem for Reasoning & Automation" width="100%">
</p>

# N.Y.R.A.

**Neural sYstem for Reasoning & Automation**

N.Y.R.A. is an open, modular AI assistant architecture designed to combine natural interaction, intelligent reasoning, persistent memory, contextual awareness, and real-world automation.

At its core, Nyra uses a centralized Router to orchestrate specialized services for reasoning, skills, memory, voice, identity, and external capabilities while maintaining consistent context, security policies, observability, and distributed tracing across the entire request lifecycle.

> Understand the user, understand the context, reason when necessary, and act deterministically whenever possible.

The project is self-hosted, observable, extensible, reproducible, and independent from any single automation platform or AI provider. Home Assistant is the first automation platform integrated with Nyra.

## Project status

Nyra v1 is under active development.

- **Milestone 1 — Router foundation and observability: complete.**
- **Milestone 2 — Home Assistant adapter and Nyra speaker integration: complete.**
- **Milestone 3 — Identity and Voice: complete.**
- **Milestone 4 — Memory and context: complete and deployed in production.**
- **Milestone 5 — Skills: complete and deployed in production.**

Milestones 2 and 3 established the production Home Assistant speaker path and
trusted voice identity lifecycle. A physical Nyra speaker has been validated
end-to-end through Home Assistant, Router, and the dedicated Speaker-ID
service, including enrollment, Wake Word sample capture/export, session-scoped
identity, localized identity responses, observability, and persistent fresh-CT
deployment.

The remaining specialist migration is Milestone 6 LLM access; deterministic Skills and Home Assistant capability execution now use the Nyra v1 Router lifecycle.

## Milestone 2 capabilities

- Thin native Home Assistant conversation adapter.
- Synchronous request forwarding through `POST /v1/requests`.
- Stable speaker `source_id` propagated from ESPHome through Home Assistant to Router.
- Read-only `Nyra Source ID` diagnostic entity for deterministic speaker discovery.
- Authenticated Home Assistant user context for `ha_assist`; speaker requests do not infer personal identity.
- Router event bridge to Home Assistant and ESPHome for real-time interaction state.
- Semantic speaker LED states for listening, transcription, identification, local/global processing, tool use, clarification, speaking, and errors.
- Protected two-blink identity feedback for recognized, unrecognized, and changed identity outcomes.
- TTS playback lifecycle feedback without overwriting identity transients.
- Session-close audio/visual feedback.
- Canonical local micro-wake-word models `Nyra IT` and `Nyra EN`, selectable through Home Assistant while replacing the stock base wake-word models.
- Physical end-to-end validation on a Nyra ESPHome speaker.

## Milestone 3 capabilities

- Dedicated reproducible `nyra-speaker-id` service with ECAPA-TDNN inference.
- Parallel Router audio relay with strict request/session/source correlation.
- Typed `IDENTIFIED`, `NOT_RECOGNIZED`, and `FAILED` biometric outcomes.
- Router-owned trusted identity resolution and per-wake-word speaker sessions.
- Home Assistant voice-profile enrollment and editable Wake Word sample capture.
- Nyra Admin profile, diagnostic, audio-review, deletion, and export views.
- Runtime threshold, margin, and timeout configuration with persisted snapshots.
- Identity latency/outcome metrics and privacy-safe lifecycle observability.

## Milestone 4 capabilities

- Dedicated Memory service with SQLite/WAL persistence and local multilingual embeddings.
- Structured aliases, mappings, defaults, and shortcuts with deterministic user, family, and system precedence.
- Identity-scoped facts, preferences, notes, and relations with explicit confirmation, supersession, and physical deletion.
- Router lifecycle gate that searches semantic memory only when a matched Skill declares it optional or required.
- Router-only management APIs and Nyra Admin pages showing human names alongside stable Home Assistant IDs.
- Debian 12 service bootstrap, readiness and reboot verification, consistent backup, guarded restore, and rollback documentation.
- Localized identity and failure responses without spoken technical IDs.


## Milestone 5 capabilities

- Dedicated deterministic Skills service with a stable Router/Skills protocol.
- Router-owned Home Assistant resource resolution and capability execution; Skills has no direct Home Assistant credentials.
- Deterministic light/switch/cover actions with ambiguity-safe target clarification.
- Persisted ephemeral Jobs with restart recovery semantics and Admin visibility.
- Persistent and one-shot Behaviors materialized only through the Router-owned Home Assistant automation capability.
- Explicit remember, forget, and supersede intents routed through the Router-owned Memory authorization gateway.
- Distributed Skills/capability spans preserving request, trace, parent-child, and async origin correlation.
- Router-backed Nyra Admin diagnostics for registered Skills, Jobs, service readiness, and capability status.
- Future LLM action proposals constrained to Router -> Skills validation/materialization -> Router capability.
- Reproducible Debian 12/systemd deployment, verification, backup, guarded restore, and physical production validation.

## Documentation

- [Nyra speakers](docs/SPEAKERS.md) — reference hardware, ESPHome, Home Assistant integration, provisioning, and speaker lifecycle.
- [Wake words](docs/WAKE_WORDS.md) — the `nyra_it` / `nyra_en` model policy, Google Colab training notebooks, real and synthetic datasets, and how to train a custom wake word.

## Core principles

- Centralized orchestration through Nyra Router.
- Specialized services with clearly defined responsibilities.
- No direct communication between first-level Nyra services.
- Centralized capability authorization and policy enforcement.
- Persistent contextual and operational memory.
- Deterministic execution whenever possible.
- AI reasoning only where it provides actual value.
- Centralized structured logging and distributed tracing.
- A single administration and observability interface exposed by Router.
- Reproducible deployments.
- No hardcoded installation-specific addresses or credentials.
- Provider-independent architecture.

## Repository language

All source code, comments, documentation, configuration examples, API names, log events, and commit messages are written in English.
