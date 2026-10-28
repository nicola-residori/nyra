# Persistent voice alarms, personal calls, and timers

Status: approved by user on 2026-10-28; implemented on feature branch, physical acceptance pending.

## Intent and requirements

Implement on a feature branch based on main (inspected baseline
`0b2ecd8fb580033ddf7191129129604ffcb1a39a`). No merge to main without separate
authorization. Use observed TDD RED/GREEN, targeted tests, full suite and
`git diff --check`; commit/push only after green verification.

Italian commands: `svegliami tra/alle`, `metti una sveglia`, `chiamami tra/alle`,
`metti un timer di`. Provide corresponding English commands and localized
confirmations, list/cancel/stop commands. Never guess an ambiguous job target:
ask for clarification. Default list and management scope is the origin speaker;
explicit job selection must remain within that scope.

Alarms and timers have distinct sounds. Their audible playback lasts at most
60 seconds, configurable downward only. Personal calls are a single TTS
utterance, with a duration phrase for relative requests and a clock phrase for
absolute requests. Persist the requested duration/clock, language, timezone,
origin source, and an optional display-name snapshot. Include that name only
when the request's trusted identity resolution source is
`SPEAKER_IDENTIFICATION`; continuity, HA identity, guest, failures, missing name
and technical user IDs must never provide a spoken name.

## Existing contracts and approach

Skills `JobStore` already persists SQLite/WAL jobs and atomically claims due
work. `JobScheduler` currently executes HA actions sequentially and recovers
RUNNING jobs as UNKNOWN_OUTCOME. `stop_job` deliberately rejects unsupported
stops. Extend these contracts without changing recovery semantics for HA actions.

`EspHomeSpeakerOutput.announce` currently sends `assist_satellite.announce`,
and silently does nothing without a target. This is not an acknowledged,
restart-safe deferred-audio capability. Add a typed audio start/status/stop
contract exposed through Skills -> Router -> authenticated HA adapter -> exact
ESPHome source. Router owns HA credentials and source authorization. Synchronize
the vendored HA shared protocol and test canonical module compatibility.

Alternatives considered: HA automations alone would move job ownership away
from Skills and duplicate diagnostics/recovery. Fire-and-forget event delivery
would confuse acceptance with playback and lose stop/restart guarantees.
The proposed approach retains Skills job ownership and gives audio an explicit
lifecycle. The user has supplied priority requirements following this proposal;
the written design was subsequently approved.

## Audio ownership and wake word

Priority: wake word > notifications/alarms/timers/calls > conversation. This
defines arbitration with existing announcements, not a new notification product.
Unrelated music must not be stopped by job cancellation. Alerts interrupt an
active conversation and prevent late conversation TTS from playing over them.
On one speaker, equal-priority alerts use due-time FIFO; different speakers
progress independently. Pending jobs are not cancelled by a wake word.

Wake-word detection locally stops the active alert, disables any repeat,
invalidates queued audio belonging to that interrupted playback generation, and
updates a persistent-in-HA job lifecycle report when connected. It must also
interrupt a conversation if both paths are active. No network round-trip may
be required for silence. A single wake word silences the current playback;
the existing firmware's silence-first behavior is preserved rather than
automatically starting a second Assist session.

The current vendor firmware checks active voice_assistant before announcing
audio and includes a legacy 15-minute timer. Those paths must not permit an
alert to continue after wake detection or bypass the 60-second cap. Dedicated
alert ownership must distinguish local alert playback from unrelated media.

Playback owns SPEAKING only while actually audible. Stop, natural end, timeout,
error and wake interruption restore the current semantic/idle LED state while
preserving protected identity transients. Late callbacks cannot restore stale
state or restart interrupted audio. The physical firmware enforces the cap
even if HA or Skills disconnects.

## Delivery, concurrency, and restart

Use job ID as an idempotency key, with source-scoped playback ownership.
Acceptance is distinct from STARTED and terminal COMPLETED/STOPPED/FAILED.
Cancellation affects SCHEDULED work; stop targets queued/active audio with an
explicit safe-stop contract. Never report COMPLETED on HTTP acceptance alone.

Persist jobs before confirmation. On Skills restart, preserve future schedules
and reconcile active alert IDs against HA playback state. Do not blindly replay
audio whose delivery outcome is unknown. HA restart/ESP reboot silence active
audio and make the interrupted outcome explicit; retain future jobs in Skills.
Use bounded retries for confirmed offline/not-started delivery within a
configurable grace window (proposed default 60 seconds from due time), then
mark MISSED/FAILED with diagnostics. Never reroute to another speaker. Ambiguous
transport outcomes require status reconciliation, not an unconditional start.
Prevent duplicate starts, cancel/claim races, stale stop callbacks and one
offline speaker blocking all other jobs.

Absolute times use an explicit configured installation timezone (example
Europe/Rome), never the service host timezone. Persist execution instants in
UTC. A clock-only request selects the next occurrence; reject/clarify nonexistent
or ambiguous daylight-saving times. Relative durations must be finite and
positive; malformed or unsupported input yields a localized clarification.

## Implementation boundaries and validation

Add focused alert parsing/Skill, audio protocol/client/gateway and HA playback
coordinator modules rather than embedding audio in generic HA operations.
Extend job storage/scheduler, registration/configuration, Router wiring and
ESPHome package/vendor wake handling. Keep stable source-ID discovery; never
hardcode installation entity IDs or credentials.

Test parser and locale/time boundaries, exact identity eligibility, persistence,
concurrent jobs, source isolation, cancel/claim races, offline expiry,
idempotency, restart reconciliation and UNKNOWN_OUTCOME. Test Router/HA contract
round trips and actual playback state transitions separately from HTTP success.
Add firmware configuration/compile checks and assertions covering local wake
stop, priority and timeout. Existing HA-action tests must remain green.

Prepare deployment order: back up database/config/HA/firmware; deploy compatible
contracts and HA/firmware before enabling the new Skills capability; health and
readiness checks; rollback instructions preserving operator configuration.
Provide a macOS Bash 3.2 runner ZIP if it simplifies reproducible operator checks.
No production deployment is included in this design's authorization.

Physical validation must cover known/unknown speaker, Italian/English calls,
two concurrent timers, different sounds, 60-second cutoff, wake interruption
during conversation and alert, offline/reconnect, Skills/HA/ESP restarts, and
LED restore. Software tests cannot certify acoustic wake detection or the real
speaker lifecycle; report those limits explicitly.
