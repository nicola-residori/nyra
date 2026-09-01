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
- **Milestone 3 — Identity and Voice: next.**

Milestone 2 established the production Home Assistant ingress/egress boundary and the real-time speaker interaction path. A physical Nyra speaker has been validated end-to-end through Home Assistant and Router, including stable source identification, Router-driven interaction states, protected identity feedback, TTS lifecycle feedback, and the custom Italian `Nyra` wake word.

The previous implementation remains only a functional reference for specialist services that have not yet been migrated to the Nyra v1 lifecycle.

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
- Custom local micro-wake-word model for `Nyra`, while retaining the base speaker wake words.
- Physical end-to-end validation on a Nyra ESPHome speaker.

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
