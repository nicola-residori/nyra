# Idle battery and alarm indicator

Opt-in status for the 7-LED ring: battery retains front LEDs 6/0/1; the alarm uses
opposite LEDs 3/4. Three alarm LEDs can be configured at 2/3/4. The regions never
overlap. Armed modes (including pending/triggered) are fixed red; disarmed is dark;
arming or unknown/unavailable state is slow amber blinking. Brightness defaults to
20% and the base battery thresholds/colors remain unchanged.

Listening, speaking, identity, closing, volume feedback, boot/network and timed audio
effects retain priority. The firmware resumes the composite gauge only when idle.
No alarm-control command is issued; the optional package reads a configured HA state
through the existing encrypted native API. A HA voice-client disconnect invalidates
the cached alarm state; a reconnect replays the current state, including unchanged
states. Startup never restores a previously armed value from flash.

## Configuration

Add the optional package and the actual alarm entity to each private device entrypoint:

```yaml
packages:
  device: !include devices/your-speaker.yaml
  alarm_status: !include packages/nyra-alarm-status.yaml
substitutions:
  nyra_alarm_entity: alarm_control_panel.your_house_alarm
  nyra_alarm_led_count: "2"  # 2 or 3
  nyra_idle_indicator_brightness: "0.2"
```

The shared speaker package supplies the renderer, disabled unless the optional
package is enabled. The alarm entity is installation-specific and is not a shared
default. The diagnostic text sensor “Nyra Alarm Indicator State” mirrors its state.
Rings smaller than five LEDs cannot safely show both regions; the alarm overlay is
then suppressed. A three-LED overlay needs at least six ring LEDs.

The existing HA battery updater must set only “Nyra Battery Gauge Percent”. Remove
its `light.turn_on`/effect action: periodically forcing the gauge can overwrite a
conversation. Firmware now restores idle appearance; HA supplies the battery value.
Use the existing battery source and target numbers unchanged.

## Validation and rollback

Native tests cover state mapping, two/three LED layouts, bounds, battery preservation,
armed/disarmed/unknown transitions and busy/idle priority. Validate merged device
configuration, build both devices and verify encrypted OTA/reconnect stability.
Test armed rendering with fixtures; real alarm arming is not needed for deployment.
Physical armed-color acceptance is checked during the user's normal alarm use.

Back up shared sources, device entrypoints, keys and the battery automation before
rollout. Deploy both firmware images before removing the old effect action. Rollback
must restore both the old firmware/source configuration and the automation effect
action. Preserve unrelated automation YAML, existing credentials and entity identity.

## Intrusion siren

The optional alarm-status package also reacts to `triggered` on each configured
speaker. A distinct embedded alternating siren interrupts conversation and ordinary
Nyra alerts. Unlike wake-up alarms/timers, **wake does not stop this siren and does
not open listening while it is active**. Explicit HA `disarmed` stops it; otherwise
its local watchdog stops it at 60 seconds. The existing announcement volume is used;
it is not forced to maximum.

Repeated `triggered`, unknown/unavailable states and reconnect within the same boot
do not restart/extend an episode. Only explicit `disarmed` resets the latch. After
reboot, a received `triggered` state starts one new bounded siren. Offline speakers
receive nothing until reconnect; loss of HA cannot disable the local cutoff, but a
disarm cannot be received while disconnected. Both speakers subscribe independently.
Ordinary remote alert STOP and native wake/timer/sound actions cannot cancel the
protected siren. This does not prevent power loss or direct external media controls.

The asset is procedural mono 16-bit PCM at 16kHz: 2 seconds alternating 740/1040Hz
every 250ms, 8ms edge envelopes, peak amplitude 10500. No external sound licensing.
Validation uses synthetic triggered/disarmed states; no real alarm-control action
is needed. An audible physical test is separate from software/deployment validation.
