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

### Create a new speaker

Run the provisioning script from the repository root. The two positional parameters have different purposes:

```bash
python3 tools/new-speaker.py speaker-01 "Living Room Speaker"
```

In this example:

| Parameter | Example | Purpose |
| --- | --- | --- |
| `device_name` | `speaker-01` | Unique and stable technical identifier for the physical speaker. Nyra also uses it as the speaker `source_id`. |
| `friendly_name` | `Living Room Speaker` | Human-readable name shown by ESPHome and Home Assistant. It is not the Nyra protocol identity of the speaker. |

The `device_name` / `source_id` must be unique across the Nyra speakers in one installation and should remain stable for the lifetime of that physical speaker.

The identifier does not encode the room. The speaker's physical location is represented by its **Home Assistant Area**. For example, `speaker-01` can be assigned to the `Living Room` Area and later moved to the `Office` Area without changing its `source_id`.

The exact accepted characters for `device_name` are enforced by the provisioning script and ESPHome; a room-based naming convention is not part of the Nyra architecture.

With the default output location, the example command creates:

```text
esphome/devices/speaker-01.yaml
esphome/device_secrets/speaker-01.yaml
esphome/speaker-01.yaml
```

The files have different roles:

- `esphome/devices/speaker-01.yaml` contains the non-secret per-device configuration and stable `source_id`.
- `esphome/device_secrets/speaker-01.yaml` contains generated per-device secrets such as the API encryption key and OTA password. It is installation-specific, gitignored, and must never be committed.
- `esphome/speaker-01.yaml` is the ESPHome Device Builder entrypoint for that physical speaker.

The generator refuses to overwrite existing device or private-secret files.

### Copy the required files to Home Assistant

The generated per-speaker files depend on the shared Nyra ESPHome package and canonical wake-word artifacts.

For `speaker-01`, Home Assistant should contain:

```text
/config/esphome/speaker-01.yaml
/config/esphome/devices/speaker-01.yaml
/config/esphome/device_secrets/speaker-01.yaml
/config/esphome/packages/nyra-speaker.yaml
/config/esphome/models/nyra_it.json
/config/esphome/models/nyra_it.tflite
/config/esphome/models/nyra_en.json
/config/esphome/models/nyra_en.tflite
```

From the repository root on the development machine:

```bash
ssh root@homeassistant.local 'mkdir -p /config/esphome/devices /config/esphome/device_secrets /config/esphome/packages /config/esphome/models'

scp esphome/speaker-01.yaml root@homeassistant.local:/config/esphome/
scp esphome/devices/speaker-01.yaml root@homeassistant.local:/config/esphome/devices/
scp esphome/device_secrets/speaker-01.yaml root@homeassistant.local:/config/esphome/device_secrets/
scp esphome/packages/nyra-speaker.yaml root@homeassistant.local:/config/esphome/packages/
scp esphome/models/nyra_it.json esphome/models/nyra_it.tflite esphome/models/nyra_en.json esphome/models/nyra_en.tflite root@homeassistant.local:/config/esphome/models/
```

The package and wake-word artifacts are shared by all Nyra speakers. They only need to exist once in the Home Assistant ESPHome tree, but they should match the repository version used to provision the speaker.

### Validate, install, and configure

In **ESPHome Device Builder**:

1. Open the generated `speaker-01` device.
2. Run **Validate**.
3. Run **Install** and flash the physical board.
4. Wait for the device to reconnect.

Then in Home Assistant:

1. Add the discovered ESPHome device.
2. Assign the device to the correct **Home Assistant Area**. This is the speaker's room/location and is independent from `source_id`.
3. Enable **Allow the device to perform Home Assistant actions** on the ESPHome integration entry.
4. Select the Nyra conversation agent in the Assist pipeline used by the device.
5. Confirm that the read-only diagnostic entity **Nyra Source ID** exists and matches `speaker-01`.
6. Select `Nyra IT` or `Nyra EN` as the wake word.
7. Trigger the wake word and verify the complete physical path through ESPHome, Home Assistant, Router, TTS, and the speaker.

Subscribing to device logs is useful for diagnostics but is not required for normal operation.

### New-speaker checklist

1. Choose a unique and stable technical `device_name` / `source_id`.
2. Choose a human-readable `friendly_name`.
3. Run `tools/new-speaker.py`.
4. Keep the generated `device_secrets` file private.
5. Copy the three generated speaker files to Home Assistant.
6. Ensure the shared package and both canonical wake-word models are present on Home Assistant.
7. Validate and install the device from ESPHome Device Builder.
8. Add it to Home Assistant and assign its Area.
9. Enable Home Assistant actions for the ESPHome integration.
10. Configure the Assist pipeline and wake word.
11. Verify **Nyra Source ID** and perform a physical wake-to-response test.

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

The canonical Nyra speaker exposes two local wake-word choices:

- **Nyra IT** — `nyra_it.json` / `nyra_it.tflite`
- **Nyra EN** — `nyra_en.json` / `nyra_en.tflite`

Both are exposed through Home Assistant's native ESPHome wake-word selection. The stock upstream Alexa and Okay Nabu models are replaced and are not presented as separate choices.

The pinned Waveshare package also contains a `Wake word sensitivity` selector whose lambda refers directly to the upstream IDs `alexa` and `okay_nabu`. Nyra therefore preserves those IDs only as internal compatibility anchors and replaces their model definitions with `!extend`:

```yaml
micro_wake_word:
  models:
    - id: !extend alexa
      model: /config/esphome/models/nyra_it.json
    - id: !extend okay_nabu
      model: /config/esphome/models/nyra_en.json
```

The manifests provide the user-visible names `Nyra IT` and `Nyra EN`. The inherited IDs are implementation details and must not be treated as the public wake-word names.

Nyra's language-specific wake-word models and the training workflow are documented separately:

- [Wake words and custom training](WAKE_WORDS.md)

Keeping wake-word training separate from speaker provisioning is intentional: the same reference speaker can load different local models without changing the Home Assistant/Router architecture.
