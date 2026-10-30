# Apple Music / AirPlay rollout — 2026-10-30

## Delivered

Music Assistant stable 2.10.9 installed as the HA app, boot auto and host networking.
Nicola created the local admin account and authorized Apple Music directly in the UI.
No password/token was copied into repository or chat. The native MA HA integration
was confirmed from Supervisor discovery, using its existing internal trust/token.
Only physical Nyra Mansarda/Soggiorno were selected in the HA player provider and
AirPlay Receiver. A transient selection of another discovered “Soggiorno” player was
corrected to the two actual Nyra players before acceptance; no audio was sent to it.

Nyra adds a typed musical semantic/Skills route and authenticated Router → HA
capability. Stable source/device/physical-player/MA-registry joins prevent display-name
routing. Apple-only catalog search, bounded clarification, live queue controls and
source default are implemented. Synchronized grouping returns explicitly unsupported
until that transport is configured/tested; adding is distinct from transferring.

## Evidence

- Protocol, skill, gateway, registry, catalog choice, room clarification, retry,
  deadline and mixer regressions observed RED then GREEN.
- Independent review returned two material findings: room pending state swallowed
  unrelated utterances; request-ID-only caching rejected clarification resumed under
  the same Router request ID. Both reproduced/fixed with regressions. That reviewer
  then hit an environment usage limit, so its complete branch review did not finish;
  remaining checks were performed inline and through live/native tests.
- Real HA 2026.10.4 source and live service validation showed search limit belongs
  at top level; `search_options` is a UI grouping, not service payload. Fixed RED/GREEN.
- Live LLM misclassified “anche” as transfer and inferred destination from source;
  prompt examples plus authoritative grounding distinguish GROUP/TRANSFER and remove
  unspoken destination areas. “Parliamo dei Queen” cannot cause playback even if
  the model proposes it. Final real-provider/bridge checks passed for free artist
  query, explicit-room jazz, contextual volume, additive playback and conversation.
- Full suite **1053 passed**, one existing dependency warning, 23.33 seconds. A clean
  clone of committed `c648e8f` independently passed **1053**, warning unchanged,
  25.53 seconds; unrelated uncommitted wake-model changes were not needed for tests.
- Diff checks and compileall passed. A first macOS tar attempt included AppleDouble
  metadata; compileall stopped deployment before backend restarts. Clean Python-made
  archives and removal of only those metadata files fixed packaging.
- Router, Skills and LLM report ready. HA core check passed and new authenticated
  music endpoint responds after restart. Real registry joins map Nyra physical
  entities to MA entities. Apple search returns catalog artists.
- End-to-end authenticated Router request “Fammi ascoltare qualcosa dei Queen”
  returned `needs_clarification`, `continue_conversation=true`, three catalog choices,
  no error. It did not select/play a candidate or produce a real TTS/audio test.
- Both firmware builds passed ESPHome 2026.10.1, encrypted OTA and 65-second repeated
  API stability checks. Build time 2026-10-30 20:48:02 +0100; Soggiorno config hash
  `0x3db004d2`, Mansarda `0x45fd436b`. Both mirrored disarmed, idle gauge and
  `run002|running=1|Ehi Nira=1:179|Nira=1:179`; siren remained `none|IDLE`.
- Local mDNS discovered both RAOP services: “Nyra Mansarda | Music Assistant” and
  “Nyra Soggiorno | Music Assistant”. UI confirms both selected and receiver Running.

## Revisions and limits

Music/firmware implementation `d8651b9`; bounded search/client budgets `0a05ac2`;
semantic grounding and usage docs `c648e8f`. Router/LLM include final semantics;
Skills uses the music implementation; HA includes bounded coordinator; firmware
uses the music mixer changes and preserves separately installed run002 wake assets.

Physical audio, iPhone playback, pause/wake recognition over music and restoration
remain pending user feedback. Discovery and API checks do not establish audible
playback or robust acoustic detection. Multiroom synchronization remains disabled.
MA AirPlay Receiver is alpha with documented buffering around five seconds. Apple
integration is unofficial and can require reauthorization. Older timer-wake acoustic
acceptance and unexplained room-light activation are not claimed fixed here.
No real burglar-alarm trigger/control or main merge was performed.

## Rollback

Protected code/config backups on their hosts:
`/opt/backups/nyra-router-before-music-20261030.tgz`,
`/opt/backups/nyra-skills-before-music-20261030.tgz`,
`/opt/backups/nyra-llm-before-music-20261030.tgz`;
HA `/config/nyra-backups/20261030/music-before.tgz`.
Restore only relevant application/shared code, preserve all live databases, runtime
secrets and run002 wake-model package/assets. LLM environment remains untouched in
`/etc/nyra/llm.env`. Rebuild previous firmware with retained private entrypoints and
current wake models; OTA and repeat stability checks. MA's account/provider data
persists separately; do not delete it to roll back Nyra voice code. Disable only
its two receiver selections if reception itself needs rollback. Never export private
firmware binaries or auth-containing backups in the verification ZIP.
