# Alarm Status Chimes Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline. Steps use checkbox syntax.

**Goal:** Local arming/disarming feedback on both configured Nyra speakers.
**Architecture:** Deduplicated state edges feed the existing bounded alert owner;
embedded WAVs use the single-shot announcement lifecycle and existing wake stop.
**Tech Stack:** ESPHome YAML, native C++17 tests, Python pytest.
**Spec:** docs/superpowers/specs/2026-10-31-alarm-status-chimes-design.md

## Global Constraints
No main merge; preserve unrelated wake model work. Never arm/disarm the real alarm
for verification. No replay after reconnect; no replacement of active alerts.

## Review Focus
Bootstrap/reconnect silence; duplicate states; intermediate arming states; siren
priority/disarm; wake cancellation and LED restore.

### Task 1: State edges and single-shot audio
- [x] Write native transition and actual YAML callback tests plus WAV checks.
- [x] Run targeted tests and observe missing-feature RED.
- [x] Implement state reducer, local assets and alert-owner adapter.
- [x] Run focused tests then full pytest and git diff --check.
- [x] Review diff, compile firmware preserving private config/current wake models.
- [x] Commit/push only green tested changes, deploy both and verify stability.
- [x] Record results and remaining physical listening check.

Completed 2026-11-01. Evidence and remaining physical acceptance are in
`docs/verification/2026-11-01-alarm-status-chimes.md`.
