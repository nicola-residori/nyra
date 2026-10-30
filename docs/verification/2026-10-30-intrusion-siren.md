# Protected intrusion siren — 2026-10-30

## Behavior

Both opted-in speakers react locally to the existing HA alarm's `triggered` state.
The distinct embedded siren preempts conversation and ordinary alerts. **Wake does
not stop it or open listening.** Explicit `disarmed` stops it early; otherwise the
local 60-second watchdog stops it. Only disarmed resets the episode latch. Repeated
triggered/unknown/unavailable/reconnect states do not restart a stopped episode in
the same boot. A reboot while triggered can start one new bounded episode.

## Test and review evidence

- Native ownership/episode tests observed RED before implementation, then GREEN.
  Covers duplicate states, loss/recovery of state, wake immunity, ordinary-alert
  preemption, deadline across millis wrap, disarm and rearm.
- Native C++ execution of the actual HA on-value YAML callback covers preemption,
  old-job STOPPED publication, duplicate rejection and disarm during startup.
- YAML integration guards cover wake, native timer/scheduled alarm, native sound
  playback, ordinary remote alert commands and selection of the distinct asset.
- Independent review found unguarded API `start_va` could rearm the conversation
  output gate during intrusion. Regression observed RED, then guarded API start.
- Final combined suite including the concurrently updated wake models: **1020
  passed**, one existing dependency warning, 22.01 seconds. `git diff --check` passed.
- Both initial/final siren builds passed ESPHome 2026.10.1. Deployment builds also
  preserve the newly installed Ehi Nira/Nira model assets and startup configuration.

The temporary exported-source check initially lacked Git/index metadata needed by
the git-ignore assertions. Restoring the tracked-example index fixed the fixture;
the siren source snapshot independently passed **1020 tests**, one existing warning,
21.49 seconds. A concurrent wake-model
change briefly caused two old model-name assertions to fail in the shared workspace;
that task updated those assertions before the passing combined run above.

## Deployment and physical validation

Source alarm read before rollout: `disarmed`. No alarm-control action, real trigger
or audible siren test was performed. Siren source revision: `647c485`, combined with the existing installed run002 wake
models. Model/base-package SHA-256 values were checked against HA sources before
rollout. Combined ESPHome 2026.10.1 build time: 2026-10-30 20:16:39 +0100;
Soggiorno config hash `0xda641950`, Mansarda `0x6b830b70`.
Both encrypted OTA uploads succeeded. Each device passed 65 seconds of repeated
encrypted API reads with stable build time, alarm mirror `disarmed`, idle gauge
active, and alert status `none|IDLE` (no siren started). Both reported
`run002|running=1|Ehi Nira=1:179|Nira=1:179`, confirming preserved models.

Physical acceptance remains pending: during an agreed safe sound test or normal
alarm use verify both speakers, distinct sound, wake immunity, disarm stop and local
cutoff. A simulated software state does not establish acoustic output/volume.
Power/network availability can prevent playback; disconnected devices cannot receive
a disarm, but the local cutoff still runs. Direct external media controls are outside
the protected Nyra alert/wake API. Existing timer wake recognition remains unaccepted.

## Rollback

Protected HA source backup before siren work:
`/config/nyra-backups/20261030/intrusion-with-run002-before.tgz` (includes private entrypoints,
secrets and automations; do not export). This snapshot includes the installed wake
models; preserve them when reverting only siren code. Rebuild prior alert/status/vendor sources
with the current wake-model package and private configuration, OTA both devices,
and verify encrypted API stability. No HA automation change is needed for siren.
No merge to main was performed.
