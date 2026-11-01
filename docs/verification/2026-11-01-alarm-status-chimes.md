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
  33.09 seconds. `git diff --check` passed.
- Independent read-only review found no blocking correctness gaps.
- Coverage limitation: intrusion/chime callbacks are compiled separately; their
  combined ordering was reviewed, rather than exercised together in one harness.
- Soggiorno firmware compiled successfully with ESPHome 2026.10.1:
  config hash 0xbc9b3cf4, build time 2026-10-31 21:41:46 +0100.

## Deployment and physical acceptance
Deployment checks will be recorded below. No real alarm arm/disarm/trigger calls
are used by the developer. During the user's next ordinary arm/disarm cycle,
check one/two beeps on both speakers and normal idle battery/alarm LED restore.
Audibility, room volume and real HA reconnect behavior require physical acceptance.

Existing deployed run002 wake models and private device credentials are preserved;
unrelated wake-model work is excluded from the commit. Rollback is a rebuild of
the preceding source using retained private configurations and current wake assets.
