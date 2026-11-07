# Voice alerts deployment verification — 2026-10-29

Runtime application code: `fd0028b2294663114690af03adc6db7f89bdf92b` on
`feat/persistent-voice-alerts`. Main remains unmerged.

## Preflight and backups

- Router, Skills and Home Assistant were reachable and healthy before changes.
- Production Router/Skills code was compared with the main baseline before copying;
  the older, uncommitted production layout was preserved rather than reset.
- Scoped HA component/ESPHome source backup, Router code/config backup and Skills
  code/config/consistent SQLite backup were checksum-verified before deployment.
- Home Assistant's ESPHome app configuration was also backed up through Supervisor.
- Operator credentials, per-device YAML/identity and persistent data were preserved.
  Backups contain private configuration and were not added to Git or the ZIP runner.

## Compatibility gates

The actual environment was HA 2026.10.4, ESPHome Device Builder 2026.10.1 and
previous speaker firmware 2026.9.0. Local private build copies preserved the real
keys and substituted only installation paths and build parallelism.

Full ESPHome 2026.10.1 builds passed for both production speakers:

- Speaker A configuration hash: `0xd24c74be`.
- Speaker B configuration hash: `0xb4420817`.

Both OTA uploads succeeded over encrypted connections. Each device reconnected
with firmware 2026.10.1, exposed all three audio entities and passed a 65-second
boot stability guard. No production keys or binary firmware images are published.

Two environment-discovered issues were fixed before enabling the new service path:

1. Const embedded AudioFile descriptors in ESPHome 2026.10: generated application
   compilation reproduced RED; the native compatibility adapter test passed GREEN
   against both old and new playback signatures. Full firmware builds then passed.
2. HA Cloud TTS requires regional locale names: live `it` failed while `it-IT`
   completed. Four provider-boundary tests reproduced RED and passed GREEN after
   locale resolution. Live `it` and `en` then both completed correctly.

Final full software regression: **973 passed**, one dependency deprecation warning.
Python compilation, Bash syntax and `git diff --check` passed before commit/push.
The native VoiceAssistant override remains pinned to the reviewed 2026.8.2 runtime;
its application, runtime and API callers were also checked against 2026.10.1.

## Observed live results

| Probe | Observed result |
|---|---|
| HA component configuration/startup | Configuration check passed; RUNNING 2026.10.4 |
| Authenticated HA audio API | STATUS returned typed NOT_FOUND for a disposable ID |
| Router | HEALTHY / READY; systemd active |
| Skills | Ready, deployment verifier passed; voice_alerts enabled |
| Concurrent timer/alarm on separate speakers | Both ACCEPTED -> PLAYING -> COMPLETED |
| Safe stop of ringing alarm | PLAYING -> STOPPED confirmed by device state |
| Italian and English calls | Both ACCEPTED -> PLAYING -> COMPLETED |
| Scheduled call through full service chain | SCHEDULED -> RUNNING -> COMPLETED; no name for unrecognized synthetic UI caller |
| Persistent future timer | Remained SCHEDULED across controlled Skills restart, then cancelled through Router |
| Simulated unavailable source | Bounded expiry to FAILED / SPEAKER_OFFLINE_EXPIRED |
| Independent source during unavailable-source retries | Another full scheduled call completed |
| Cleanup | No active test jobs; terminal diagnostic records retained; SQLite integrity ok |

Synthetic direct-UI requests can leave semantic visual feedback because they do not
have the real Assist pipeline's terminal lifecycle. Those test visuals were cleaned
up on the two Nyra status rings; no unrelated lights or media were changed.

## Remaining physical acceptance

Telemetry proves device playback/stop state, not what a person hears or says.
Still check real wake interruption during ringing, slow TTS and conversation;
recognized/unknown speaker names; language and audible sound distinction; and LED
restoration during actual conversational/identity transients. Follow the matrix in
`docs/voice-alerts.md`. Physical voice acceptance and main merge remain separate.

## Physical feedback and wake sensitivity correction

The user reported that the timer was created, but wake interruption did not seem
to work on one speaker, and quiet recognition also required many repetitions.
The user timer's telemetry showed completion at the 60-second cap rather than
STOPPED. This was not accepted as a passing wake test.

Live microWakeWord configuration showed Nyra IT 0.90 / Nyra EN 0.85, while both
unchanged trained manifests specify 0.70. The stock Waveshare sensitivity table
was still using Alexa/Nabu calibration after replacing those models with Nyra.
Commit `38d6a25` makes sensitivity relative to each model's trained default and
adds a non-transcript wake-running diagnostic at alert start. Native regression
RED/GREEN and the 973-test suite passed; both full ESPHome 2026.10.1 builds and OTA
uploads succeeded and both devices passed the stability guard again. The affected
speaker now reports 0.70 / 0.70 and retains its selected Nyra IT model.

Firmware source revision: `38d6a25` (server/HA application code is unchanged from
`fd0028b`). Final firmware configuration hashes: speaker A `0x02f9d1f6`, speaker B
`0x8a8d61ab`. The physical wake/identity acceptance remains pending a repeated user
test; the correction is not reported as acoustically verified yet.
