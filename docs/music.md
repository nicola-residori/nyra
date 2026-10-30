# Apple Music and phone AirPlay

Music Assistant supplies the Apple catalog, library and queues. Nyra interprets
natural music requests through a separate typed semantic/Skills branch, Router
capability and authenticated HA adapter. A music discussion does not imply playback;
unspoken destination areas are removed before execution. No raw entity IDs, service
names or stream URLs can be supplied by semantic music commands.

## Use

Without a destination, new playback starts on the speaker receiving the request.
Examples include “fammi ascoltare Queen”, “riproduci un po’ di jazz in mansarda”,
“pausa”, “riprendi”, “cambia pezzo”, “più basso”, and “volume al trenta per cento”.
Artist/album/track/playlist/radio queries are searched on Apple Music; ambiguous
results ask which of up to three results to use. Reply “la prima”, “la seconda” or
“la terza”. An unknown room asks for a room while retaining the original request.
A new command/topic replaces that clarification. Transfer uses the source speaker's
live queue and requires a named destination; it never guesses another room's queue.

“Mettila anche in mansarda” means add playback, not move it. Synchronized grouping
is deliberately not enabled on these ESPHome HA players until transport support
and physical synchronization are verified. Such requests return an explicit limitation;
Nyra never starts independent streams while claiming they are synchronized.

## AirPlay

On the same local network, select “Nyra Soggiorno | Music Assistant” or
“Nyra Mansarda | Music Assistant” in the iPhone's AirPlay audio picker. This relays
phone audio through MA to the existing speaker music pipeline. The phone remains
the source. This is an audio receiver, not a claim of screen mirroring/native
AirPlay2 certification. MA's receiver plugin is alpha and its buffering can cause
about five seconds of start/pause/resume latency. Track navigation for arbitrary
phone audio may remain with the sending app; absent a controllable queue, Nyra says so.
See https://www.music-assistant.io/plugins/airplay-receiver/.

## Priority and context

A single local mixer attenuation owner recomputes from live states: active alert
or native timer 60dB, voice/wake handoff 30dB, other announcements 20dB, idle 0dB.
It never changes/restores the player's volume setting or calls resume. Thus ending
an old conversation cannot release an active alert's attenuation, and music stopped
or changed by the user is not resumed from a stale snapshot. The existing intrusion
siren still ignores wake; only disarm or its 60-second cutoff stops it.

HA resolves each stable Nyra Source ID through its device's physical ESPHome player
and the MA registry unique ID. Names alone are not trusted. Missing/duplicate/offline
mappings produce an explicit error. Catalog choices are opaque, source/session bound,
expire in 120 seconds and are revalidated before playback. Retries are idempotent
per request and musical step, allowing clarification under the same Router request ID.
Room clarification expires and remains bound to its source/session. The semantic
layer handles room answers; pending room state never captures every new utterance.

The coordinator bounds work to 10 seconds. Gateway/client budgets are 12/15/18
seconds from HA back through Skills and Router; ordinary Skills retain their
configured default timeout. Slow search is cancelled before deferred playback.

## Setup and acceptance

Install stable MA, add its native HA integration and Home Assistant player provider,
select only the two Nyra physical media players, and expose those through the
AirPlay Receiver plugin. Login to Apple is performed by the account owner in MA;
credentials/tokens are not entered into Nyra config or committed. Apple integration
is unofficial, requires a subscription and may need reauthorization (documented
180-day token expiry): https://www.music-assistant.io/music-providers/apple-music/.

Verify catalog search, spoken clarification/control, phone AirPlay selection and
actual sound in both rooms. Test wake recognition over music and alert attenuation/
restoration without triggering the real burglar alarm. Discovery/API success does
not prove audible output, synchronization or robust acoustic wake recognition.
