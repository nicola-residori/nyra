# ESPHome Nyra speakers

Nyra speakers use one shared ESPHome package and tiny per-device files. The device/source ID is the stable correlation key used by Home Assistant and Router events.

## Secret model

Secrets have two different scopes and must stay separate:

- **shared installation secrets**: Wi-Fi credentials live in the normal local `/config/esphome/secrets.yaml` because every speaker uses them;
- **device-local secrets**: each speaker gets its own API encryption key and OTA password in `/config/esphome/device_secrets/<device-name>.yaml`.

The per-device file is not the global ESPHome `secrets.yaml`. It is a private substitutions file loaded only by that speaker's top-level YAML. `esphome/device_secrets/*.yaml` is gitignored.

Example private file, generated automatically:

```yaml
api_encryption_key: "..."
ota_password: "..."
```

Do not commit either real shared or device-local secret values.

## Prerequisites

- Home Assistant ESPHome Device Builder.
- The Waveshare ESP32-S3 Audio board used by the Nyra speaker reference hardware.
- `/config/esphome/wakewords/nira.json` installed locally.
- `wifi_ssid` and `wifi_password` in the local `/config/esphome/secrets.yaml`.
- `esphome/assets/nyra_close.wav` copied to `/config/esphome/assets/nyra_close.wav`.

If `/config/esphome/secrets.yaml` does not exist yet, create it only for shared ESPHome secrets:

```bash
cat > /config/esphome/secrets.yaml <<'EOF'
wifi_ssid: "YOUR_WIFI_SSID"
wifi_password: "YOUR_WIFI_PASSWORD"
EOF
chmod 600 /config/esphome/secrets.yaml
```

## Create a speaker

From the repository root:

```bash
python tools/new-speaker.py nyra-camera "Nyra Camera"
```

The command creates exactly three instance artifacts:

```text
esphome/devices/nyra-camera.yaml
esphome/nyra-camera.yaml
esphome/device_secrets/nyra-camera.yaml   # private, gitignored
```

The first contains non-secret instance parameters. The second is the ESPHome Device Builder entrypoint. The third contains randomly generated credentials used only by that speaker.

There are no room-specific secret names such as `nyra_camera_api_key` in the shared configuration.

## Existing versioned device without local secrets

A repository checkout may already contain a versioned device definition, such as `nyra-mansarda`, while its private secret file is intentionally absent. Generate only the missing local secret file with:

```bash
python tools/new-speaker.py nyra-mansarda "Nyra Mansarda" --secrets-only
```

This creates:

```text
esphome/device_secrets/nyra-mansarda.yaml
```

without modifying the versioned device YAML.

## Deploy to Home Assistant

Create the target directories once:

```bash
mkdir -p /config/esphome/packages \
             /config/esphome/devices \
             /config/esphome/device_secrets \
             /config/esphome/assets
```

Copy the common package/assets and the selected speaker's three instance files to the corresponding paths under `/config/esphome/`. Keep `device_secrets/<device>.yaml` private on the machines that need to compile/manage that device.

Then validate and install the top-level configuration, for example:

```text
/config/esphome/nyra-mansarda.yaml
```

The first installation over USB establishes Wi-Fi; subsequent updates use that device's own OTA password.

## Runtime contract

The common package exposes a stable Home Assistant light named `Nyra Status Ring` with these effect names:

- `nyra_listening_white_fast`
- `nyra_identifying_warm_white_comet`
- `nyra_identity_green_2blink`
- `nyra_identity_red_2blink`
- `nyra_identity_blue_2blink`
- `nyra_processing_local_turquoise_comet`
- `nyra_processing_global_rainbow_comet`
- `nyra_using_tool_yellow_comet`
- `nyra_speaking_purple_audio`
- `nyra_error_red`

It also exposes the `Nyra Close Feedback` button. Home Assistant uses that button for the atomic local close chime + blue blink sequence. Wake-word activation audio remains local to the Waveshare voice-assistant package.

The public effect names are an interface. Their internal animations may evolve without changing the HA adapter.

## Adding the next room

Adding another identical speaker requires no copied firmware logic and no edits to shared secrets:

```bash
python tools/new-speaker.py nyra-camera "Nyra Camera"
```

Only the generated non-secret device definition/entrypoint and its gitignored private credentials are new.
