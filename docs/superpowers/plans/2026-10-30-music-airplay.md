# Music and AirPlay Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, with one final fresh review.

**Goal:** Apple Music and phone AirPlay on existing Nyra speakers with natural context-aware control.
**Architecture:** Strict shared music command, semantic Skills branch, Router capability,
authenticated HA adapter over MA services and live registry/queue state. MA stable
server supplies Apple catalog and AirPlay receivers. No arbitrary IDs/URLs from LLM.
**Tech Stack:** Python/Pydantic/pytest, HA/MA, ESPHome C++/YAML if ducking requires changes.
**Spec:** docs/superpowers/specs/2026-10-30-music-airplay-design.md

## Global Constraints

Source speaker default. Preserve current wake/siren. No main merge. Apple login by
Nicola only after server/UI ready. Multiroom sync not claimed before physical check.
No arbitrary external side effects in tests. Preserve unrelated dirty wake-model files.

## Review Focus

Semantic branch must reject mixed actions and raw IDs. Music cannot become a HA scene.
Registry duplicate/missing/ambiguous/offline mappings fail without fallback.
Clarification expires after 120s, binds source/session and rechecks fresh candidates.
AirPlay/MA/no-queue live state determines which controls can run; no stale cross-room queue.
Ducking ownership must survive overlap and avoid resuming/stale-volume writes.

### Task 1: Protocol and semantic music routing

Files: shared/protocol/music.py, semantic.py, router/semantic_skill_bridge.py,
llm/prompts.py, skills/modules/music.py, skills/modules/__init__.py,
skills/modules/home_assistant.py; mirrored HA shared protocol.
- [ ] RED typed command validation and separate semantic routing; contextual/natural
  examples, confidence and mixed generic actions rejected.
- [ ] GREEN MusicCommand actions PLAY/PAUSE/RESUME/STOP/NEXT/PREVIOUS/VOLUME/TRANSFER/GROUP,
  optional area names and free query/type; no raw URL/entity/service fields.
- [ ] RED/GREEN skill precedence, pending choice/expiry/source binding, localized replies,
  and generic scene negative cases. Metadata carries typed command only.

### Task 2: Trusted music execution

Files: router/music_capability.py, router/api/music.py, router/app.py;
HA music_api.py/music.py and initialization/discovery.
- [ ] RED source-to-player fresh registry join and contextual live state tests.
- [ ] GREEN authenticated Router-to-HA endpoint, source stable ID to physical media
  player to MA entity; registry unique IDs must match upstream hass-player mapping.
- [ ] RED/GREEN Apple-only bounded search and server-owned opaque candidate tokens,
  120-second/source/session binding and fresh revalidation before play. No arbitrary URI.
- [ ] RED/GREEN real MA service dispatch; no-match/ambiguity/offline/auth errors truthful.
  Transfer/group only when supported; never silently play independently as synchronized.

### Task 3: Server, AirPlay and priorities

- [ ] Install stable MA HA app with persistent data; add HA integration/provider.
  Expose only the two discovered Nyra players as separately named AirPlay receivers.
- [ ] Inspect existing local media ducking during listening/TTS/alerts. RED/GREEN
  ownership regression before any needed firmware change; preserve live music and
  do not restore stored player volume or auto-resume stopped playback.
- [ ] Prepare Apple provider login UI for user; continue independent work while pending.

### Task 4: Verification/release

- [ ] Targeted/full suite and diff check. Fresh review; reproduce/fix material findings.
- [ ] Back up and deploy Router/Skills/HA; config/build/OTA only if needed, preserving
  deployed wake models. Authenticated live non-audible readiness/discovery tests.
- [ ] Commit/push green, draft PR, docs/current state/runner. Keep physical music,
  AirPlay, over-music wake recognition and multiroom synchronization clearly pending
  until user acceptance; no real intrusion trigger.

Ruling: user authorized the described MA approach and said proceed including AirPlay;
no new preference or repeated approval gate is needed. Builder review settled separate
music semantics, trusted registry join, bounded choices and concurrent audio ownership.
