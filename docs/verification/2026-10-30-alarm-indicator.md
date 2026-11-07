# Idle alarm indicator — 2026-10-30

Two opposite red LEDs (3/4 on the seven-pixel ring) indicate armed status, only at
idle. Battery pixels 6/0/1 remain unchanged. Disarmed is dark; arming/unknown is
slow amber blinking. Read-only HA state; no alarm control was performed.

## Evidence

- Native C++ RED/GREEN tests cover exact state mapping, two/three-pixel layouts,
  bounds, battery preservation, transitions and all idle-priority flags.
- Review found native timer ringing could be overwritten between announcements.
  A test compiling the actual YAML lambda reproduced the failure; adding the
  ringing flag passed. The same harness reproduced/fixed wake-listen handoff
  priority before the microphone becomes active.
- Full Python suite: **1017 passed**, one existing dependency deprecation warning,
  19.91 seconds. `git diff --check` passed before code commit.
- Both real merged device configurations compile with ESPHome 2026.10.1. The
  integration build exposed custom-enum include ordering; storing a zero-initialized
  byte with explicit enum casts fixed it while preserving native semantic tests.
- Initial encrypted OTA succeeded on Soggiorno and Mansarda. Each passed repeated
  encrypted API reads for 65 seconds, mirrored `disarmed`, and displayed the idle
  gauge. Final wake-handoff firmware is source revision `9d4043b`: build time
  2026-10-30 20:00:55 +0100, Soggiorno config hash `0xfe694f6a`, Mansarda
  `0xb36fb8d0`. Both final encrypted OTA uploads succeeded. Each final device
  passed another 65-second stability check, mirrored `disarmed`, and exposed the
  active idle gauge via encrypted API.
- HA battery automation now updates only the existing battery number targets;
  its forced light/effect action was removed. Semantic comparison preserved all
  other automations. `ha core check` passed; reload waited for no running automation.
- Local ESPHome SDK inspection confirms same-state HA replay invokes the callback.

## Limits and physical acceptance

Armed/unknown layouts are covered by fixtures. No real alarm arming/disarming was
performed. During normal alarm use, verify two red pixels opposite the battery,
then disappearance after disarming; listening/speaking must hide the idle overlay.
This feature does not improve acoustic wake-word recognition during timer audio.
Main remains unmerged.

## Rollback

Private HA backup: `/config/nyra-backups/20261030/alarm-indicator-before.tgz`.
Restore the previous shared/device sources and battery automation together, rebuild
previous firmware with ESPHome 2026.10.1 and retained private credentials, then OTA
both devices and verify stability. No positively identified old binary was retained.
Do not distribute firmware binaries: they contain installation credentials.
