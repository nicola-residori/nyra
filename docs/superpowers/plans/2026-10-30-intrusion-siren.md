# Intrusion Siren Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline, task by task.

**Goal:** Sound a distinct local intrusion siren on both configured speakers.
**Architecture:** Optional HA state subscription drives an episode latch in the
existing local alert ownership core. Intrusion preempts other alerts and rejects
wake cancellation; the existing watchdog and finish path restore normal operation.
**Tech Stack:** ESPHome 2026.10.1, C++, Python pytest/native compiler.
**Spec:** docs/superpowers/specs/2026-10-30-intrusion-siren-design.md

## Global Constraints

60-second hard local cap; stop early only on disarmed; wake cannot stop/open listening.
One start per episode; reset latch only on disarmed. No real alarm trigger, no main merge.

## Review Focus

- Duplicate triggered and unknown/reconnect cannot extend or restart audio.
- Preemption must stop/report the old job and invalidate late conversation audio.
- Wake, native timer and ordinary remote STOP cannot stop the intrusion siren.
- Disarm during begin/settling must cancel all pending audio.
- Timeout across millis wrap must release ownership and restore idle LEDs.

### Task 1: Local protected intrusion ownership

Files: components/nyra_alerts/nyra_alerts.h, packages/nyra-alerts.yaml,
packages/nyra-alarm-status.yaml, vendor/waveshare-esp32-s3-audio-va-v1.0.0-core.yaml,
assets/nyra_intrusion.wav; tests/esphome/test_nyra_intrusion_siren.py.
Paths above are relative to esphome/ except tests/.

- [ ] RED native state tests for episode latch, protected wake, preemption,
  duplicate rejection, disarm, timeout/wrap and rearm after disarmed.
- [ ] GREEN `IntrusionEpisode.observe(state)` and `AlertState.start_intrusion(now)` /
  `protected_audio()`; keep all ordinary alert semantics unchanged.
- [ ] RED integration tests of actual YAML callbacks for trigger/disarm/preemption
  and wake/native-timer/sound guards. GREEN state subscriber and protected routing.
- [ ] Generate distinct embedded alternating siren, register and select locally.
- [ ] Targeted tests then full suite; real merged configs and both full builds.
- [ ] Fresh reviewer checks change; reproduce/fix material findings RED/GREEN.
- [ ] Diff check, commit/push green, back up source, OTA both, encrypted state and
  stability checks without playing siren or manipulating the real alarm.
- [ ] Record evidence, physical test limits, rollback and update draft PR/runner.

Ruling: continue inline on the existing feature branch because the user explicitly
said proceed; no additional execution-method or design approval round is needed.
