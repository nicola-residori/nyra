# Voice alarms, personal calls, and timers

Feature branch only. This change is not a production deployment or an authorization
to merge main. The implementation extends Skills jobs, adds a typed Router audio
capability and HA delivery ledger, and uses a local ESPHome ownership/watchdog core.

## Voice commands

| Function | Italian | English |
|---|---|---|
| Alarm | Svegliami tra dieci minuti; metti una sveglia alle 7:30 | Wake me in ten minutes; set an alarm at 7:30 |
| Personal call | Chiamami tra 10 minuti; chiamami alle quindici | Call me in ten minutes; call me at 15:00 |
| Timer | Metti un timer di un minuto e 30 secondi | Set a timer for one minute and 30 seconds |
| List | Elenca i timer / le sveglie / le chiamate / gli avvisi | List timers / alarms / calls / alerts |
| Cancel pending | Annulla il timer / la sveglia / la chiamata | Cancel the timer / alarm / call |
| Stop active | Ferma il timer / la sveglia / la chiamata | Stop the timer / alarm / call |

Commands are scoped to the original stable `source_id`. Several matching jobs
cause a clarification; answer `il primo` / `il secondo`, `the first` / `the second`,
or supply a returned job ID. Lists order by execution time. No cross-speaker
cancellation and no fallback playback on another speaker.

Positive numeric durations (decimal comma/point), compound units, and common
Italian/English number words are supported. Italian `un'ora` and `mezzora` are
supported. Absolute clocks are 24-hour clock-only requests for the next occurrence.
An incomplete command asks for a duration/time. Unsupported wording, zero,
negative/nonfinite durations, more than 366 days, invalid clocks and DST gaps/folds
ask for clarification rather than silently scheduling a guessed time.

Personal calls say a duration for relative requests and local clock time for
absolute requests. The optional name is a snapshot of the trusted display name
only when the current request has `SPEAKER_IDENTIFICATION`. HA identity, continuity,
guest, failure, and technical user IDs never supply a name. Calls play once.

## Defaults and priorities

Skills environment:

| Setting | Default | Meaning |
|---|---|---|
| `NYRA_ALERT_TIMEZONE` | `Europe/Rome` | Installation timezone; UTC persisted |
| `NYRA_ALERT_MAX_SECONDS` | `60` | Alarm/timer local cutoff, configurable 1–60 only |
| `NYRA_ALERT_OFFLINE_GRACE_SECONDS` | `60` | Retry window for confirmed OFFLINE/BUSY, measured from due time |

The firmware clamps the local deadline to at most 60 seconds even if a caller is
misconfigured. Loading/settling time counts toward that deadline; audible playback
can therefore be shorter. A call has the same safety watchdog and is never looped.
Alarm and timer WAV tones are distinct, embedded, procedurally generated assets.

Priority is wake word > alerts/notifications > conversation. A wake word stops all
active announcement/alert paths locally, disables repeat, and advances an audio
epoch so late TTS cannot start. It leaves future scheduled jobs intact. A single wake silences the active audio and starts a fresh listening request after
the prior pipeline and announcement have stopped. The handoff remains pending
while cancellation settles; a newer wake restarts it, and mute or an alert cancels it. Software microphone mute
still disables wake detection. No system can detect a wake word while its mic is muted.

Alerts stop the active voice-assistant pipeline. The HA adapter suppresses late
Router speech and fallback speech if audio ownership changed. Actual announcement
playback drives SPEAKING; stop/end/watchdog restore the saved base LED state and
preserve identity transients. Unrelated music is not cancelled; announcement mixing
continues to use the device's existing media pipeline.

Existing Nyra HA notifications (including enrollment feedback) use the same audio
ownership path and one-shot firmware behavior. Their language is retained. A busy
source returns an explicit BUSY result rather than interrupting an equal-priority
alert; the caller may retry. General future notification scheduling is not introduced
here. Raw third-party media calls outside Nyra cannot be made safe by Router policy alone.

## Delivery and persistence

`POST /v1/capabilities/audio` is the Skills -> Router boundary. Router uses its
existing HA URL/token to call authenticated `POST /api/nyra/alerts`. Contract:
`AlertRequest` START/STATUS/STOP, `job_id`, `source_id`, kind, language, message and
max_seconds; `AlertResponse` NOT_FOUND/OFFLINE/BUSY/ACCEPTED/PLAYING/COMPLETED/
STOPPED/FAILED/UNKNOWN_OUTCOME. HTTP acceptance is never playback completion.
The private-network service trust boundary remains the project's existing one.

Skills SQLite/WAL stores future jobs and origin correlation. Alert RUNNING jobs
survive Skills restart and query the HA ledger; legacy HA-action recovery remains
UNKNOWN_OUTCOME. HA persists its delivery ledger under `.storage/nyra_alerts_<entry>`
before sending audio, keyed by job ID. On HA restart it reconciles active jobs with
the firmware diagnostic state, never blindly replaying unknown delivery. Keep the
HA ledger with backups: removing it destroys deduplication evidence.

Discovery uses original entity names on the exact source device:
`Nyra Alert Command`, `Nyra Audio Epoch`, `Nyra Alert State`. Registry renames are
supported. HA prepares a complete TTS URL using its preferred Assist pipeline
(or optional config-entry option `alert_pipeline_id`) and the request language;
that TTS engine must support the requested language. Alarm/timer audio needs no TTS.
The pinned ESPHome 2026.8.2 `voice_assistant` external component also guards native
conversation TTS ingress and deferred playback with a local generation token.
Every wake invalidates that token; a new pipeline must start before native speech
is allowed again. Preserve and explicitly rebase this runtime patch on ESPHome upgrades.

Long URLs are staged in job-bound <=255-character command chunks, then START is
accepted only with the original firmware epoch. No text or URL is restored from
flash as a command. Firmware reboot silences playback and changes the epoch.

Same-speaker jobs are FIFO, different speakers progress independently. Confirmed
offline/busy starts retry within grace; expired jobs become FAILED. Queued jobs
whose due time is old can expire if the device remains unavailable/busy when their
turn arrives. Ambiguous transport failures remain RUNNING for status reconciliation,
then UNKNOWN_OUTCOME after grace + 60s. Unknown jobs are not replayed automatically.
A stop persists intent and reports STOPPED only when preparation was cancelled
before delivery, firmware confirmed stop, or the local wake event confirms silence.

Job/HA ledgers currently retain terminal records (including a call's spoken message
and optional name) for operator diagnostics and deduplication. Protect backups and
storage as personal data; no new automatic retention pruning is included.

## Rollout and rollback

1. Pin the tested feature commit. Back up operator env/configuration, Skills jobs
   DB with SQLite backup while online (or stop service for a consistent file copy),
   Router code/config, HA `custom_components/nyra`, HA alert storage, ESPHome YAML,
   firmware and all `esphome/assets`, models and components. Never overwrite secrets.
2. Deploy the complete HA custom component **including bundled shared protocol**.
   Restart HA and run its configuration check. Future jobs still belong to Skills.
3. Install the complete ESPHome packages/vendor, `components/nyra_alerts/`, the pinned `components/voice_assistant/` override,
   `assets/nyra_alarm.wav`, `assets/nyra_timer.wav`, and existing assets/models.
   Build with ESPHome 2026.8.2 or 2026.10.1 (both validated). Existing installation
   `/config/esphome` paths and private device entrypoints remain operator-managed.
   Upload only an installation-specific, reviewed build to the intended source.
   Enable HA action/event permissions for the ESPHome device, as required by existing
   Nyra feedback events. Verify new diagnostic/command entities are enabled.
4. Deploy Router, restart, verify `/health` and `/ready`. Audio gateway reuses
   `NYRA_HOME_ASSISTANT_URL` / token configuration already present in Router.
5. Deploy Skills, preserve its DB and protected `/etc/nyra/skills.env`; set timezone
   explicitly and restart. Verify `voice_alerts` is enabled and readiness remains green.
6. Run the verifier, then the physical matrix below. Do not claim physical acceptance
   from HTTP acceptance, generated firmware or mocked HA services.

Rollback: stop new scheduling and cancel pending alert jobs first. Stop active
playback or wait for the local 60s cap. Restore reviewed Router/Skills/HA/firmware
versions and configuration together. An old scheduler cannot execute voice-alert
payloads, so do not start old Skills against unreviewed pending new jobs. Preserve
ledger backups and reconcile interrupted jobs manually instead of resending them.
No destructive schema migration is required; job payloads remain JSON.

## Verification and physical acceptance

```bash
PYTHON_BIN=.venv/bin/python bash deploy/verify/voice-alerts.sh
# Optional full firmware build, no upload:
PYTHON_BIN=.venv/bin/python ESPHOME_CONFIG=/path/to/private-device.yaml bash deploy/verify/voice-alerts.sh
```

The optional `NYRA_ROUTER_URL` / `NYRA_SKILLS_URL` checks read health/readiness.
`NYRA_HA_URL`, `NYRA_HA_TOKEN`, `NYRA_VERIFY_SOURCE_ID` enable a read-only authenticated
STATUS probe. None of these verification paths starts an alert or changes production.
The macOS ZIP runner clones the pinned feature commit and runs software checks;
Python >=3.11, Git and a C++ compiler (Xcode command-line tools) are required.

Physical acceptance (record source, revision, timestamps and job IDs):

- Known speaker: relative and absolute calls include the recognized display name;
  unknown speaker and continuity-only requests omit it. Repeat in Italian/English.
- Alarm and timer sound different, both stop by 60 seconds; a call plays once.
- During listening, processing and spoken conversation, fire each alert type.
  Verify interruption, no late response, protected identity blinks and LED restoration.
- Wake during a ringing alarm, timer, call and slow TTS preparation. Verify silence
  without HA network, no resumed repeats, and a fresh subsequent wake works.
- Two same-source timers complete FIFO; a second source remains independent.
  List/cancel/stop and ordinal clarification affect only the requested source.
- Unplug speaker, schedule, reconnect before/after grace. Verify bounded delivery or
  explicit failed job, no reroute. Interrupt the HTTP response after acceptance and
  verify deduplication. Stop during a network outage and inspect eventual confirmation.
- Restart Skills before due and during playback; restart HA during active TTS;
  reboot ESPHome. Verify future schedules survive and unknown audio is not replayed.
- Repeat while music is playing; music must remain available after the announcement.

Native C++ tests prove the local ownership core, timeout, epoch rejection and millis
wraparound. HA/Router integration tests prove contract and lifecycle behavior.
Acoustic wake detection, amplifier behavior, firmware event timing and real LED
restoration still require the physical speaker checks above.

Contract references: [HA Assist Satellite](https://www.home-assistant.io/integrations/assist_satellite/),
[HA TTS media source API](https://github.com/home-assistant/core/blob/2026.8.3/homeassistant/components/tts/media_source.py),
[ESPHome template text](https://esphome.io/components/text/template/), and
[ESPHome speaker media player](https://esphome.io/components/media_player/speaker/).

### ESPHome 2026.10.1 compatibility

The deployment preflight also compiled the real device configurations with
ESPHome 2026.10.1. That version makes embedded AudioFile descriptors const.
`nyra::AudioFilePointer` keeps the script parameter schema valid and
`nyra::play_asset` adapts the old mutable-pointer and new const-pointer playback
signatures without changing playback behavior. The native C++ regression exercises
both signatures. The guarded VoiceAssistant runtime remains based on 2026.8.2;
its generated application, runtime and API callers were also checked against
2026.10.1 and both full firmware builds succeeded.

### TTS provider locale resolution

A request language such as `it` is resolved to the provider's advertised locale
(e.g. `it-IT`), preserving the preferred pipeline locale/voice when its language
matches. Generic English uses the preferred English locale, otherwise advertised
`en-US`; underscore/hyphen locale spelling is normalized. Explicit regions are
preserved, and unavailable or ambiguous provider languages fail explicitly rather
than speaking in a different language. This also applies to notifications.

### Nyra wake sensitivity

The sensitivity selector now uses each Nyra model's own trained manifest cutoff.
The default “Slightly sensitive” level preserves that cutoff (about 0.70 for the
current models); “Moderately” and “Very” lower it by about 0.10 and 0.20, bounded
above zero. Stock Alexa/Nabu cutoffs must not be reused after replacing their
models with Nyra. The saved sensitivity choice and model files are preserved.
Firmware debug logs report whether the wake detector is running at alert start.

## Conversational listening (2026-10-30)

Router explicitly returns `continue_conversation`, independently of request completion.
Skills commands and executed LLM action plans finish without reopening the mic unless
clarification is needed. General conversational responses reopen after playback, even
without a question. A completed conversational turn gets a new request in the same
session; clarification keeps the request ID. Bounded history includes both sides and
intermediate clarification answers. SQLite adds nullable response/history columns
without replacing existing request records.

Exact whole utterances `grazie`, `chiudi`, `ok grazie`, `ok` close deterministically
(case/punctuation insensitive). English equivalents include `thanks`, `thank you`,
`close`, `okay`, `okay thanks`, `ok thanks`. A longer command such as “ok accendi la
luce grazie” still executes. Microphone capture follows the native Assist silence
limit; there is no unconditional continuous microphone loop. A later wake starts a
fresh session and stale/cancelled responses cannot delete it.

Physical acceptance must verify single-wake stop **and** listening, a two-turn general
conversation without a question, a clarification/answer round, a command that does
not reopen, and an explicit closing phrase. Wake detection/VAD sensitivity remains
separate from handoff correctness; the previous physical test needed repeated wakes.

Intrusion exception: the opt-in HA alarm-status package uses a separate local siren
on `triggered`. It preempts ordinary alerts and ignores wake until disarmed or the
60-second cutoff. See docs/alarm-indicator.md. Ordinary wake-up alarms/timers/calls
retain their existing wake interruption behavior.
