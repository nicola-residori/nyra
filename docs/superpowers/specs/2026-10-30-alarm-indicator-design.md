# Idle alarm indicator

User requested 2–3 fixed red LEDs for an armed home alarm, disjoint from the battery
LEDs, and selected idle-only visibility. Chosen layout: battery remains indices
6/0/1 on a 7-LED ring; alarm uses 3/4 (two LEDs), configurable to three at 2/3/4.
Listening, speaking, identity, closing, boot/network and alert effects take priority.

The optional firmware package subscribes read-only to a per-install HA alarm entity
via the existing encrypted native API. No alarm-control services or LLM are involved.
Armed modes/pending/triggered map to red; disarmed to off; arming/unknown/unavailable
to a slow amber blink (builder default to avoid implying disarmed when unknown).
The VA HA-client disconnect invalidates the cached alarm state; same-state replay
on reconnection is supported by the upstream text-sensor callback.

The battery effect is composed with an alarm overlay, preserving battery code and
LED indices. Pure C++ rendering is tested for non-overlap, bounds, transitions and
battery colors. An opt-in local idle loop restores the composed effect only when
all interaction/transient ownership is idle. Existing installation battery automation
will retain value updates but stop forcing effects every five minutes. Brightness
defaults to the installation's existing 20%; two alarm LEDs are the default.

Installation entity IDs and secrets remain outside shared source defaults. Optional
package configuration is documented with placeholders. Full tests, independent review,
ESPHome builds, backups and encrypted OTA verification precede acceptance. No real
alarm arming/disarming is part of testing; armed rendering uses native unit fixtures.
