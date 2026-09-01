# Nyra Speakers

Nyra speakers are ESPHome voice-assistant endpoints connected to Home Assistant. They are deliberately thin edge devices: they capture the wake word and voice input, expose a stable source identity, play Home Assistant TTS, and render Nyra's real-time interaction state. The Router remains the orchestration authority.

## Reference hardware

The current Nyra reference speaker is the **Waveshare ESP32-S3-AUDIO-Board**.

Waveshare describes it as an ESP32-S3 smart-speaker development board with:

- ESP32-S3R8 dual-core MCU, up to 240 MHz
- 16 MB Flash and 8 MB PSRAM
- dual-microphone array
- ES7210 audio ADC / microphone codec
- ES8311 audio DAC / speaker codec
- onboard speaker amplifier
- seven circular RGB LEDs
- USB-C
- optional battery support
- TF/microSD, display, and camera interfaces

Nyra currently uses the audio and RGB capabilities; the extra expansion interfaces are not required.

Official hardware documentation:

- https://docs.waveshare.com/ESP32-S3-AUDIO-Board
- https://www.waveshare.com/wiki/ESP32-S3-AUDIO-Board

The ESPHome base configuration used by Nyra is derived from the community project linked by Waveshare itself:

- https://github.com/MichalZaniewicz/esphome-waveshare-esp32-s3-audio-va

Nyra pins that upstream package to a known version and layers project-specific behavior on top of it.

## Software stack

The speaker path is:

```text
microWakeWord
    |
    v
ESPHome speaker
    |
    v
Home Assistant Assist
    |
    v
Nyra Home Assistant adapter
    |
    v
Nyra Router
    |
    +---- response ----------> Home Assistant TTS ----------> speaker
    |
    +---- realtime events ---> Home Assistant bridge -------> status ring
```

The speaker does not contain Nyra's reasoning logic. It is an input/output endpoint for Home Assistant and Router.

## Install ESPHome in Home Assistant

Nyra's reference deployment uses the **ESPHome Device Builder** add-on in Home Assistant.

Install it from the Home Assistant add-on store, start it, and open its web interface. The speaker is then compiled and installed from Home Assistant rather than requiring a local ESPHome CLI.

The shared Nyra speaker package is deployed to:

```text
/config/esphome/packages/nyra-speaker.yaml
```

Per-device YAML remains installation-specific and must not be committed to the public repository with real Wi-Fi credentials, room names, static addresses, or secrets.

## Provision a speaker

Every physical Nyra speaker must have its own stable source identifier. This value is used throughout the path:

```text
ESPHome device -> Home Assistant -> Nyra Router
```

The value is exposed in Home Assistant as the read-only diagnostic entity **Nyra Source ID**. It is the deterministic join key used by the Home Assistant adapter to route Router events back to the correct physical speaker.

A speaker source is not a person. Nyra never treats the source ID as proof of human identity.

After provisioning:

1. Build and install the ESPHome configuration.
2. Add the discovered ESPHome device to Home Assistant.
3. On the ESPHome integration entry, enable **Allow the device to perform Home Assistant actions**.
4. Select the Nyra conversation agent in the Assist pipeline used by the device.
5. Confirm the `Nyra Source ID` diagnostic entity exists and remains stable.
6. Trigger a wake word and verify the complete voice path.

Subscribing to device logs is useful for diagnostics but is not required for normal operation.

## Speaker interaction states

During an active Nyra interaction the status ring represents Router semantic state, with narrowly defined local precedence for hardware lifecycle.

The current states are:

- `IDLE`
- `LISTENING`
- `TRANSCRIBING`
- `IDENTIFYING`
- `PROCESSING_LOCAL`
- `PROCESSING_GLOBAL`
- `USING_TOOL`
- `WAITING_CLARIFICATION`
- `SPEAKING`
- `ERROR`

Identity feedback is a protected two-blink transient for recognized, unrecognized, or changed identity outcomes. Actual TTS playback owns the local speaking visual state without truncating that transient.

## Wake words

Wake-word recognition runs locally on the ESP32 through ESPHome `micro_wake_word`.

Nyra's language-specific wake-word models and the training workflow are documented separately:

- [Wake words and custom training](WAKE_WORDS.md)

Keeping wake-word training separate from speaker provisioning is intentional: the same reference speaker can load different local models without changing the Home Assistant/Router architecture.
