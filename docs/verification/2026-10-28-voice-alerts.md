# Voice alerts software verification — 2026-10-28

Base: main `0b2ecd8fb580033ddf7191129129604ffcb1a39a`.
Branch: `feat/persistent-voice-alerts`. Physical deployment/acceptance pending.

## Observed RED/GREEN evidence

Tests were introduced before their corresponding implementation/fix. Initial
missing-module failures identified absent components; subsequent behavior
regressions were observed failing with the named assertion before correction.

| Test group | Observed RED | Observed GREEN |
|---|---|---|
| Voice parser | 18 failures against initial stub | 23 passed including spoken forms/DST |
| Personal name snapshot and Skill | Missing voice_alerts module | 9 passed including identity, source, ordinal and duration clarification |
| Persistent audio jobs | Missing audio protocol | 8 passed including restart, FIFO, timeout and blocked-source isolation |
| Router/HA transport | Missing audio gateway | 5 passed including authenticated HA request and hard duration cap |
| HA coordinator | Missing coordinator | Lifecycle, wake, source isolation and restart tests pass |
| Long TTS URL | `len(command) <= 255` failed | URL chunks reconstruct exactly and respect firmware limit |
| Conversation fallback after wake | Spoken unavailable response leaked | Empty response, fallback suppressed |
| Slow source isolation | Other source blocked in both HA and scheduler | Both regression tests pass |
| Preparation/send ambiguity | TTS preparation incorrectly UNKNOWN | Preparation FAILED; ambiguous send reconciles PLAYING |
| Delayed wake event | Missing epoch-aware wake signature | New-epoch alert remains accepted |
| Native firmware core | Header absent / native compile failed | C++17 executable passes timeout, wake, duplicate, epoch and millis-wrap assertions |

Baseline before implementation: **906 passed**, one dependency warning.
Pre-review full verifier: **966 passed**, one dependency warning, approximately 15s.
Command: `PYTHON_BIN=.venv/bin/python bash deploy/verify/voice-alerts.sh`.
This includes the complete pytest suite, Python compileall and `git diff --check`.
The warning concerns dependency deprecation (`anyio` BlockingPortal through
Starlette TestClient); it is not a failing test.

## ESPHome build

ESPHome **2026.8.2** complete ESP32-S3 compilation succeeded, including generated
application C++, framework link and factory/OTA/ELF output. Final pre-review
config hash: `0x09b922b9`. Native ownership core is an external component so its
type is included before generated global declarations.

Build used an isolated test entrypoint, dummy Wi-Fi/API/OTA values, local copies
of the production packages/vendor and repository assets/models/components.
Only installation `/config/esphome` path references were redirected for local
validation. No device was contacted or flashed. Test firmware is deliberately
not a deployable artifact for the user's installation.

The build found and corrected the 2026.8.2 text-entity 255-character limit and
custom-include ordering. Existing configuration warnings include deprecated
`rgb_order`, merged OTA configuration and polling for non-internal GPIO buttons.
No firmware build errors remained.

## Limits

Tests validate software and generated firmware, not acoustic wake detection,
physical Speaker-ID accuracy, real network timing, LED visuals or audio output.
Run the matrix and rollout/rollback procedure in `docs/voice-alerts.md` before
production acceptance. No main merge is part of these checks.

## Independent review and correction pass

A fresh reviewer found four Important issues (no Critical or Minor findings):
command missing-state readiness, native late-TTS ingress, notification terminal
event loss and unbounded STOP reconciliation after device reboot. Each was
reproduced RED before the fix and the targeted regression passed GREEN.

- `test_command_missing_native_value_is_available_with_live_epoch`
- `test_lost_notification_terminal_event_is_reconciled_before_busy`
- `test_stop_after_speaker_reboot_expires_using_stored_deadline`
- Native output-gate executable test, including stale deferred callback after
  invalidation/new pipeline and unarmed RUN_START rejection.

Post-review software verifier: **969 passed**, one dependency deprecation warning.
A final ESPHome build also validates the pinned native `voice_assistant` override;
its upstream Python schema is unchanged and its license is retained. The patch
must be rebased explicitly on ESPHome upgrades.

Final release verification: `deploy/verify/voice-alerts.sh` passed **969 tests**,
Python compileall and whitespace checks. The final full ESPHome 2026.8.2 build
returned exit 0 with the guarded native sources byte-identical to the source
checkout. Config hash `0xd86febbb`; RAM 147879 / 341760 bytes (43.3%), application
flash 2204611 / 8126464 bytes (27.1%). These figures describe the test configuration,
not a flashed production device. Bash syntax checks for both verifier and macOS
runner passed. All four Important review findings have covering green regressions;
no deferred review findings remain.

## Deployment preflight — 2026-10-29

Production uses ESPHome Device Builder 2026.10.1. Compiling its generated C++
first reproduced a const AudioFile pointer incompatibility before any upload.
A native executable regression failed RED for the absent compatibility adapter,
then passed GREEN with both legacy and modern playback signatures. The generated
application, guarded VoiceAssistant and API connection source passed syntax checks
against 2026.10.1. Complete builds for both real device configurations passed;
private credentials were kept outside the repository and logs exposed no secrets.
The full suite passed again: **969 passed**, one dependency deprecation warning.

The first live HA Cloud TTS probe reproduced `it` -> FAILED while `it-IT` produced
ACCEPTED -> PLAYING -> COMPLETED. Four provider-boundary regressions failed RED for
generic/normalized Italian and English locales, then passed GREEN after resolving
against the engine's advertised locales. The full regression after this correction
completed with **973 passed**, one dependency warning. This correction changes HA
adapter code only; the verified firmware images are unchanged.
