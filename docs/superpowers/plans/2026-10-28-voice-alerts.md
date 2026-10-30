# Voice alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Persistent voice alarms, timers and personal calls with local wake interruption.
**Architecture:** Skills owns schedules, Router mediates audio, HA owns delivery state and ESPHome enforces local interruption and cutoff.
**Tech Stack:** Python, FastAPI, SQLite, Home Assistant, ESPHome.
**Spec:** docs/superpowers/specs/2026-10-28-voice-alerts-design.md

## Global Constraints
- Maximum audible alarm/timer duration 60 seconds; call once.
- Wake word > alerts > conversation; exact origin speaker only.
- Name only with current SPEAKER_IDENTIFICATION; localized IT/EN.
- RED/GREEN, full pytest, diff check before commit/push; no main merge.

## Review Focus
- DST gaps/folds and invalid durations must clarify.
- Transport ambiguity must not duplicate delivery.
- Wake interruptions must invalidate late TTS.
- Restart must preserve future jobs and reconcile active jobs.
- Offline sources must not block unrelated speakers.

### Task 1: Parsing, localized Skill and identity snapshots
Files: skills/modules/voice_alerts.py, skills/alert_parser.py, tests/skills/test_voice_alerts.py; builtin registration and Router trusted context.
Interfaces: parse_alert(text, language, now, timezone) -> parsed command; VoiceAlertsSkill.matches/execute; scheduler.schedule_alert.
- [x] Write parameterized parser and identity tests, run RED.
- [x] Implement parsing, execution and source-scoped management; run GREEN.
- [x] Verify targeted tests.

### Task 2: Typed audio boundary and persistent scheduler
Files: shared/protocol/alerts.py, skills/alerts.py, skills/jobs.py, skills/job_store.py, router/alert_capability.py, router/api/alerts.py, tests/integration/test_voice_alert_jobs.py.
Interfaces: AlertRequest(action START/STATUS/STOP, job_id, source_id, payload); AlertResponse(state); AlertScheduler.tick(now), schedule and stop.
- [x] Write persistence/offline/duplicate/restart/concurrency tests; run RED.
- [x] Implement typed clients, Router mediation and independent source progress; run GREEN.
- [x] Keep existing action jobs and recovery unchanged; verify targeted regression.

### Task 3: HA audio lifecycle and ESPHome local priority
Files: homeassistant/custom_components/nyra/alerts.py, esphome/packages/nyra-alerts.yaml, ESPHome vendor wake handling, HA setup/discovery/conversation; tests/homeassistant/test_alerts.py.
Interfaces: persistent HA ledger keyed job_id; exact source API actions; firmware alert API and lifecycle events.
- [x] Write coordinator lifecycle, source isolation, duplicate and wake/late callback tests; run RED.
- [x] Implement persistent coordinator, typed authenticated views, local cutoff/wake stop and LED ownership; run GREEN.
- [x] Validate firmware configuration/compile and HA protocol runtime compatibility.

### Task 4: Deployment and final verification
Files: docs/voice-alerts.md, deploy/verify/voice-alerts.sh, macOS runner packaging, state/roadmap updates.
- [x] Document defaults, rollout/rollback and physical test matrix.
- [x] Run full suite, targeted contracts, firmware checks and git diff --check.
- [x] Fresh whole-branch review; fix material findings RED/GREEN.
- [x] Commit and push feature branch only after green; report physical limitations.
