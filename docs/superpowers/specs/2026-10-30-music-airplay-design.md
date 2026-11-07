# Apple Music and AirPlay for Nyra

## Intent and approved behavior

Nicola uses Apple Music and authorized implementation of contextual natural voice
music plus AirPlay reception from the phone. No named destination means the speaker
receiving the request. Accept natural wording (fammi ascoltare, riproduci, metti),
free artist/track/album/playlist queries and contextual controls. Clarify real
ambiguity rather than invent a target or report success without execution.

Music Assistant (MA) manages Apple authentication/catalog/queues and exposes both
existing ESPHome music players as AirPlay receivers. Login to Apple is performed by
Nicola in the provider UI; no password/token belongs in repository, logs or chat.
Server playback does not require the phone to remain the source; AirPlay does.

## Architecture and alternatives

Chosen approach: MA next to HA, native HA integration, separate ESPHome music stream.
Skills interprets validated music requests, Router owns a typed music capability,
and the authenticated HA adapter resolves real Nyra speakers and calls documented
MA services. LLM semantic extraction handles varied wording; its output cannot
supply raw entity IDs/service names/URLs. Use live state for contextual controls.

A direct AirPlay stack on the ESP32 would compete with wake/siren memory/audio and
duplicate transport. A standalone Apple API client would duplicate MA authentication
and playback. Neither is needed. The existing MA AirPlay Receiver plugin supports
per-player advertisements and optional groups; no fake native AirPlay2 claim.

## Behavior and constraints

- PLAY defaults to the source speaker; explicit room names resolve freshly.
- Search distinguishes artist/album/track/playlist. Several plausible results ask
  a bounded clarification and execute only a selected freshly validated candidate.
- PAUSE/RESUME/STOP/NEXT/PREVIOUS/VOLUME use the selected live queue/player. Without
  an explicit destination they refer to music at the source; no guessing another room.
- Contextual add/transfer uses existing live queue. Multi-speaker synchronized
  playback is enabled only where supported/tested; unsupported grouping is explicit.
- AirPlay devices advertise Soggiorno/Mansarda on the local network. Source app
  determines transport/metadata capabilities; do not claim music-catalog search or
  next-track capability for arbitrary phone audio.
- Music is quieter while listening/speaking; restore on completion. Existing alerts
  take precedence and intrusion siren ignores wake as already agreed. Avoid stale
  volume restoration and never resume music stopped/changed by the user.
- MA unavailable/auth expired/no match/offline/ambiguous room returns truthful
  actionable feedback. No arbitrary HA control or fallback speaker.
- Preserve current wake models, alarm status/siren and private configs. No main merge.

## Delivery and verification

TDD RED/GREEN for protocol validation, semantic extraction bridge, Skills, Router
transport, HA resolution/search/controls and firmware priority where changed.
Full suite, diff check, independent review, build/OTA if firmware changes. Install
stable MA with persistent data and expose only the two known players; preserve
existing HA config. Prepare Apple login UI and ask only when that step is ready.
No paid account signup/purchase or real alarm triggering. Physical acceptance:
voice playback/control, AirPlay selection from iPhone, recognition over music,
notification/siren priority and restoration. Multiroom sync is a separate physical
acceptance condition; buffer delay around five seconds is expected for MA AirPlay.

References: music-assistant.io/music-providers/apple-music/;
music-assistant.io/plugins/airplay-receiver/;
music-assistant.io/player-support/home-assistant/;
music-assistant.io/faq/masssearch/; music-assistant.io/faq/massplaymedia/.
