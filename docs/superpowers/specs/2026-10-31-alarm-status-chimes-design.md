# Alarm status chimes

User-approved behavior: one short beep on effective arming and two on disarming,
on both Soggiorno and Mansarda, regardless of app/keypad/voice origin. The initial
state after boot/reconnect is silent. Repeated states and armed-mode changes are
silent. Arming/pending are not confirmation of effective arming.

Approaches: HA-pushed audio would introduce network playback and duplicate-event
risks; local ESPHome state subscription already drives the alarm LEDs and siren.
Use that subscription with embedded audio and the existing bounded alert owner.
This extends the approach presented to and accepted by the user.

Implementation decisions: 120ms 880Hz beep, double beep separated by 140ms;
moderate PCM amplitude with fades, speaker volume unchanged. Chimes interrupt
conversation and duck music, are wake-interruptible, never replace active alerts
or native ringing timers, expire within 2 seconds, and are never queued/retried.
Disarming stops the protected siren before playing its confirmation. LEDs use
existing ownership/restore. Unknown/unavailable and disconnect reset the baseline.
No alarm-control service is invoked for testing or deployment.
