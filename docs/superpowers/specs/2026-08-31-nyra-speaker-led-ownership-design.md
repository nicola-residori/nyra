# Nyra Speaker LED Ownership Design

**Date:** 2026-08-31  
**Status:** Approved design  
**Scope:** Milestone 2 — Home Assistant Adapter / Nyra speaker visual feedback

## Context

Nyra currently has multiple writers controlling the same ESPHome status ring:

1. the upstream Waveshare `control_leds` logic,
2. Nyra-local ESPHome hooks,
3. the Home Assistant Nyra bridge driven by Router semantic events.

Live diagnostics proved this creates races. Home Assistant successfully sends
`nyra_identity_red_2blink` to the correct speaker entity, but the upstream
Waveshare firmware overwrites it roughly 18 ms later with its own phase-5
`Wipe` effect. Home Assistant later restores the pending semantic processing
state after the identity feedback window.

The same ownership conflict also affects TTS feedback: upstream firmware and
the HA semantic bridge can overwrite each other while speech is playing.

## Design decision

During an active Nyra interaction, the status ring has one semantic owner:
**Nyra**.

The upstream Waveshare voice-assistant implementation may continue to manage
microphone, media playback, pipeline state, and other hardware behavior, but it
must not independently overwrite the Nyra status ring for pipeline phases while
Nyra owns the interaction.

This removes timing races instead of attempting to hide them with larger delays.

## Ownership model

### Local firmware-owned feedback

The speaker firmware owns feedback that must be immediate and does not require
Router round-trips:

- wake-word activation/opening sound,
- initial local listening indication before Router semantic state is available,
- actual TTS playback indication,
- terminal local/offline hardware fallback when Router/HA ownership is not active,
- local session-close sound/feedback where already defined.

### Router/HA-owned semantic feedback

Once Nyra semantic processing is active, Router events through the HA adapter
own these visual states:

- `LISTENING`
- `TRANSCRIBING`
- `IDENTIFYING`
- identity feedback:
  - recognized -> green 2-blink
  - not recognized -> red 2-blink
  - identity changed -> blue 2-blink
- `PROCESSING_LOCAL`
- `PROCESSING_GLOBAL`
- `USING_TOOL`
- `WAITING_CLARIFICATION`
- `ERROR`

`SPEAKING` is represented by the local playback lifecycle rather than by a
Router timing guess.

## State priority

Visual priority during a Nyra interaction is:

1. local terminal/error fallback if semantic control is unavailable,
2. active TTS playback,
3. transient identity feedback,
4. current Router semantic state,
5. idle.

Identity feedback remains protected for its configured visible window. Router
processing states received during the transient window are queued and restored
after the blink completes.

TTS temporarily overrides the current semantic visual only while audio is
actually playing. When playback ends, the speaker returns to the latest
semantic state if the interaction is still active; otherwise it returns to
idle/session-close behavior.

## Waveshare integration rule

Nyra must prevent upstream `control_leds` phase transitions from overwriting the
Nyra ring while Nyra ownership is active.

The implementation should make the smallest maintainable override around the
ring-writing behavior. It must not fork or duplicate unrelated Waveshare voice,
audio, wake-word, or pipeline logic.

When Nyra ownership is inactive, upstream/local fallback behavior may continue
to operate normally.

## Listening visual

`nyra_listening_white_fast` is a continuous fast white fade, not a pulse.

The visual should remain smooth and continuous while listening/transcribing and
must not be replaced by upstream phase visuals.

## Identity feedback

Identity feedback is a transient two-blink effect and must be physically
visible.

The existing state-machine protection window remains conceptually correct:
subsequent Router processing states are retained as pending state and rendered
only after the identity feedback window.

No artificial delays are added to warm-white, turquoise, rainbow, or other
semantic stages merely to make them visible.

## Speaking visual

The speaker enters `nyra_speaking_purple_audio` from the local
voice-assistant/media-player playback lifecycle, not solely from Router events.

The purple effect starts when TTS audio really begins playing and ends when
playback finishes. This applies equally to ordinary conversational responses,
spoken errors, and future Job-triggered speech.

If the current Waveshare/ESPHome stack does not expose usable PCM amplitude or
audio-level data to the light effect, the effect remains an animated purple
speaking visualization and must not be described as truly audio-reactive.

## Multi-speaker isolation

All Router/HA semantic output remains correlated by stable `source_id`.

Only the ESPHome device whose read-only `Nyra Source ID` matches the event
source may react. A second Nyra speaker must not change state because of another
speaker's interaction.

## Failure behavior

If the HA bridge cannot resolve a speaker target, it must not send the visual
command to a different device.

If the Router event stream is temporarily unavailable, the speaker may use
local fallback visuals required for basic wake/listening/playback behavior, but
no synthetic semantic processing state should be invented.

## Diagnostics

Temporary diagnostics added during root-cause analysis are not part of the
final implementation and must be removed:

- `NYRA_DIAG_*` logging in `speaker.py`,
- `NYRA_DIAG_*` logging in `esphome.py`,
- any temporary event-stream diagnostics.

Normal warning/error logging remains.

## Testing requirements

Implementation must be test-driven.

At minimum tests must prove:

- upstream pipeline phase changes cannot overwrite a Nyra-owned identity blink,
- identity feedback remains visible for the protected window,
- Router processing state is restored after identity feedback,
- listening uses the fast continuous white-fade effect,
- real TTS playback activates purple and playback end releases it,
- Router semantic events remain source-isolated,
- unavailable target resolution never falls back to another speaker,
- diagnostics are absent from production files,
- existing M2 adapter and ESPHome provisioning tests continue to pass.

## Verification

Before declaring completion:

1. run focused unit tests,
2. run the full Python test suite,
3. run ESPHome configuration validation,
4. deploy the HA integration changes,
5. flash/update the speaker firmware if required,
6. perform one live `Alexa -> Ciao` interaction while collecting HA and ESPHome
   logs,
7. verify physically:
   - white listening fade,
   - warm-white identifying,
   - visible red 2-blink for not-recognized,
   - semantic processing state restored afterward,
   - purple for the full TTS playback duration,
   - idle/close behavior at the end.

The live verification must show no upstream `control_leds` write overwriting a
Nyra-owned semantic effect during the protected interaction window.
