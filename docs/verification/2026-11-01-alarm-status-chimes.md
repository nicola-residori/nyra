# Alarm status chimes verification

## Behavior
Both configured speakers subscribe to `alarm_control_panel.antifurto` locally.
One 120ms 880Hz beep confirms effective arming; two beeps separated by 140ms
confirm disarming. Audio is embedded 16kHz mono PCM, faded, peak amplitude 6000.
Speaker volume is not changed. Initial state, reconnect, duplicate updates,
armed-mode changes and arming/pending states are silent.

Chimes use the existing alert owner, single-shot playback and 2-second watchdog.
They stop conversation output and use existing music ducking and LED restore.
Wake stops a chime. Active alerts/native ringing suppress it without replay.
Disarm stops a protected intrusion siren before its confirmation can play.
A state change missed while offline is not announced later.

## Automated evidence
- RED: all three new tests failed for absent reducer/callback/assets.
- GREEN: six focused chime/intrusion tests passed.
- Full repository suite: 1068 passed, one existing dependency deprecation warning,
  33.09 seconds. A clean clone of commit c56ac78 independently passed all 1068
  tests in 39.69 seconds. `git diff --check` passed.
- Independent read-only review found no blocking correctness gaps.
- Coverage limitation: intrusion/chime callbacks are compiled separately; their
  combined ordering was reviewed, rather than exercised together in one harness.
- Initial run002 build was never uploaded: the preflight detected newer v5-003
  models already deployed by the coordinated wake-word chat. Recovered the live
  speaker package/manifests/models before rebuilding, preserving thresholds
  Ehi Nira=153 and Nira=217. No source from that unrelated work is committed.
- Soggiorno final v5-003 firmware compiled successfully with ESPHome 2026.10.1:
  config hash 0x33b5b628, build time 2026-11-01 02:28:07 +0100.

## Deployment and physical acceptance
No real alarm arm/disarm/trigger calls
are used by the developer. During the user's next ordinary arm/disarm cycle,
check one/two beeps on both speakers and normal idle battery/alarm LED restore.
Audibility, room volume and real HA reconnect behavior require physical acceptance.

Existing deployed v5-003 wake models and private device credentials are preserved;
unrelated wake-model work is excluded from the commit. Rollback is a rebuild of
the preceding source using retained private configurations and current wake assets.

## Completed deployment — 2026-11-01

Feature commit: c56ac78, pushed to feat/persistent-voice-alerts; no main merge.
Five deployed HA source/assets files match repository SHA-256 checksums.
Code backup: `/config/nyra-backups/20261101/before-status-chimes.tgz`.

| Speaker | ESPHome build | Config hash | OTA | Native API stability |
| --- | --- | --- | --- | --- |
| Soggiorno | 2026-11-01 02:28:07 +0100 | 0x33b5b628 | success | 65 seconds, passed |
| Mansarda | 2026-11-01 02:29:55 +0100 | 0x0fbcbf2b | success | 65 seconds, passed |

Both native encrypted API probes confirmed the expected compiled firmware,
`v5-003|running=1|Ehi Nira=1:153|Nira=1:217`, idle composed battery/alarm LEDs,
HA state mirror `armed_night`, and initial alert state `none|IDLE`. This verifies
that initial synchronization did not start an antifurto confirmation or siren.
It does not replace listening to actual arm/disarm edges or a real reconnect.
Private build/upload/probe logs remain outside the repository.
