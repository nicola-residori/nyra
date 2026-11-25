# Intrusion siren on both speakers

## Intent and behavior

When the existing HA alarm entity enters `triggered`, Soggiorno and Mansarda sound
an embedded intrusion siren, distinct from the wake-up alarm and timer. Both
speakers interrupt conversation. The local deadline is at most 60 seconds.
Disarming stops the siren on both speakers. A detected wake word does not stop the siren and does not open listening while
it is active. Only disarming or the local 60-second deadline stops it.

One siren per triggered episode: repeated state publications do not restart it
after wake interruption or timeout. Disarming resets the episode latch; a subsequent triggered episode can start a
new siren. Unknown states and reconnects within the same boot do not reset it. On reconnect/boot while already triggered,
play once, bounded locally; offline speakers cannot receive the state until reconnect.
Audio priority: intrusion siren > wake/other alerts > conversation. Interrupting
another alert must publish its stopped outcome and reject late playback. Restore
normal idle LED composition after stopping. Preserve alarm/battery indicator behavior.

## Approaches

Use the existing optional HA state subscription and local ESPHome alert/watchdog
path. This fits the embedded audio, wake cancellation and LED ownership already in
production; it avoids a separate network-delivered media playback path. A new HA
media automation would duplicate cancellation and deadline handling and could race
with the existing player; it is therefore not proposed. No new Router scheduling
job is needed for this state-triggered local reaction.

## Builder choices and validation

Generate a distinct embedded siren asset at a configurable existing announcement
volume (no forced maximum volume). Use the existing configured alarm entity and
device identity, without adding alarm-control actions. Implement state-machine and
actual integration regressions RED/GREEN, targeted/full suite, diff check and both
ESPHome builds before commit/push and encrypted OTA. Never merge main. Validate
triggered/repeat/disarm/wake/priority using synthetic inputs; do not trigger the real
antifurto. Any audible live test must be separately agreed. Physical acceptance
remains pending normal use or an agreed safe sound test.
