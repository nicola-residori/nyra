# Push-to-record voice enrollment

## Problem

The first Home Assistant enrollment implementation marks a speaker source as enrolling and then reuses the next normal Assist capture. This requires the wake word and also sends the enrollment phrase through STT and the conversation agent, so Nyra answers as if the phrase were a command. It also gives the user no persistent phrase or progress display. This is not the intended enrollment experience.

Enrollment must use a dedicated microphone capture started from Home Assistant. It must not require a wake word, open a normal Assist pipeline, or produce a conversational response.

## User experience

Home Assistant owns the enrollment screen. It displays the selected Nyra speaker, language, current phrase, accepted sample count, requested sample count, the latest result, and controls to record or terminate.

For each sample, the user presses **Registra campione** once. Nyra Mansarda then:

1. suspends wake-word handling for the capture;
2. shows the existing white listening effect;
3. starts a direct microphone stream;
4. detects speech onset and the silence after speech;
5. ends and submits the stream automatically;
6. blinks green twice for an accepted sample or red twice for a rejected/failed sample.

An accepted sample advances the counter and phrase. A rejected sample leaves the counter and phrase unchanged so the user can retry. Completion leaves the profile immediately usable and performs the existing single localized completion announcement. Termination restores the idle speaker state without deleting already accepted samples.

## Architecture

### Home Assistant enrollment model and screen

The existing `EnrollmentCoordinator` remains the owner of Home Assistant orchestration and authenticated-user binding. Its state becomes observable so the UI can render `IDLE`, `READY`, `RECORDING`, `PROCESSING`, `ACCEPTED`, `REJECTED`, `FAILED`, `COMPLETED`, and `TERMINATED` together with phrase and progress.

The Home Assistant integration exposes a dedicated record-next-sample action for the active session. The screen calls that action once per sample. The action rejects anonymous users, sessions owned by another user, inactive sessions, concurrent captures, and source/session mismatches before commanding the speaker.

The existing start and terminate actions remain available as orchestration APIs. Starting an already active source returns its active session state instead of surfacing an opaque Home Assistant `Unknown error`.

The UI is a Home Assistant dashboard artifact supplied by the integration and uses Home Assistant entities/actions rather than the Admin application. It shows one phrase and `X/N` progress and never asks for a profile user ID; the authenticated Home Assistant user is always canonical.

### ESPHome capture

The `nyra_audio_ingress` component gains an explicit enrollment-capture operation independent of `voice_assistant`. Home Assistant invokes an ESPHome template button/action for the selected source. The component starts the microphone capture, waits for speech, then stops after a configurable trailing-silence interval. A hard maximum duration prevents a stuck recording. No wake word is required and no Assist pipeline is created.

During capture, the firmware temporarily suspends wake-word detection and restores it on every terminal path. Overlapping capture requests are rejected. The component emits capture lifecycle callbacks so the existing LED scripts render white while recording and the existing atomic two-blink buttons render the terminal result.

The firmware sends the same bounded PCM format already used by the audio ingress. Home Assistant correlates the source with the active enrollment session and sends explicit `ENROLLMENT` metadata to Router. Router relays the stream to Speaker-ID. The firmware does not receive or store the authenticated user ID.

Speech end detection uses audio energy with distinct speech-on and silence-off thresholds, a short required speech-on window, and a trailing-silence window. The defaults are conservative for the Mansarda microphone and remain configurable in ESPHome. If no speech begins before the maximum duration, the result is rejected rather than persisting silence.

### Result flow

Speaker-ID remains responsible for preprocessing, quality validation, sample persistence, embedding generation, and profile centroid rebuild. It returns `ACCEPTED`, `REJECTED`, or `FAILED` with a reason code.

Router records the attempt exactly once. Home Assistant updates phrase/progress and commands the speaker feedback:

- `ACCEPTED`: two green blinks; advance to the next phrase;
- `REJECTED`: two red blinks; keep the same phrase and show the localized reason;
- `FAILED`: two red blinks; keep the same phrase and show a technical failure message;
- final `ACCEPTED`: mark the session completed, blink green, and announce completion once.

Normal identification remains a separate capture path attached to ordinary Assist requests. An active enrollment never converts an ordinary wake-word interaction into an enrollment sample.

## Failure handling

All capture exit paths restore the microphone and wake-word state. WebSocket connection failure, timeout, queue overflow, invalid protocol responses, no detected speech, or Home Assistant disconnection terminate only the current attempt. They do not terminate the enrollment session or advance progress.

Home Assistant keeps the current session state after a rejected/failed attempt and permits another press. A reload recovers authoritative session state from Router rather than relying only on memory. Duplicate presses while recording are ignored or rejected with a clear localized message.

## Verification

Automated tests cover:

- record action authorization and active-session correlation;
- no conversion of normal Assist audio into enrollment audio;
- one press produces one direct enrollment stream;
- speech onset, trailing silence, no-speech timeout, and maximum duration;
- microphone/wake-word restoration for every terminal path;
- accepted progress/phrase advancement and rejected retry behavior;
- green/red semantic feedback selection;
- recovery after Home Assistant reload;
- no conversation request or TTS response for a sample.

The physical smoke test is performed only on Nyra Mansarda: start a six-sample session, record every phrase without saying the wake word, observe white capture plus green/red result feedback, complete the profile, and then confirm that a normal request identifies Nicola while still returning the requested answer.
