# Wake word: current installed configuration

As of 2026-11-25, **Soggiorno and Mansarda use the home-server Italian `Ehi Nira` provider**, not the old local ESPHome models for normal wake detection. The user confirmed recognition and a spoken response, with approximately one second of delay, and requested several days of testing without configuration changes.

Say **“Ehi Nira, che ore sono?”** naturally, without waiting between wake phrase and command. Spaced and joined pronunciations (`ei`, `hei`, `hey`, `ehinira`) are positive cases. **“Nira” alone is excluded.** There is no promise of identical performance for every pronunciation or room.

## Audio path and dependencies

ESPHome microphone → Home Assistant `nyra_wake` buffered provider → Wyoming server on the home Intel N100 → openWakeWord primary detector → Italian wav2vec2 V2 INT8 verifier + Silero VAD → existing Nyra Assist pipeline.

The PC and Colab are not needed for operation. The home server, Home Assistant and local network must remain available. The existing downstream STT/LLM/TTS services retain their existing dependencies. Wake processing and its bounded command buffer keep PCM in RAM; this change does not disable any existing downstream voice/identity functionality.

- Service: `nyra-wake.service`, `/opt/nyra-wake`, `192.168.0.16:10401` (trusted LAN; no public exposure or protocol authentication).
- HA provider: `wake_word.nyra_italian_wake`; pipeline: **Nyra - Ehi Nira** (`01m87t35th7w2nk035gqdprs0p`). Original/global default pipelines preserved.
- Primary threshold `.4`, two consecutive 80 ms frames; verifier `.2`, 2.8-second window and `.24`-second post-trigger context; VAD `.1` with `.096` seconds minimum speech; candidate refractory 2 seconds.
- HA retains up to eight seconds of PCM with one-second pre-roll, preserving commands received during verification. Two independent stream engines share the large immutable verifier session; inference is serialized to bound memory/CPU.
- Approximately one second of secondary-verifier delay was confirmed by the user. Two-client synthetic benchmarks were approximately 1.3/2.4 seconds after the primary candidate; load can increase delay. These are different measurements, not guaranteed latency limits.

## Evidence and limits

Exact exported INT8 inference was evaluated on the target N100, with frozen thresholds and 6,680 cases. All training and evaluation audio is synthetic Italian TTS; held-out voice identities overlap training identities. Augmented cases are not independent real users or hours of television.

| Metric | Validation | Held-out testing |
| --- | ---: | ---: |
| Ehi Nira hits | 927 / 945 (98.10%) | 2,767 / 2,835 (97.60%) |
| Ambient false events / synthetic exposure | 3 / 65 min | 17 / 260 min |
| Ambient events/hour | 2.77 | 3.92 |
| Hard-negative clips triggering | 4 / 120 | 14 / 600 |
| Ordinary speech clips triggering | 0 / 120 | 0 / 500 |
| Solo Nira negative controls triggering | 1 / 315 | 10 / 945 |

**The original 99% recall / ≤2 false events/hour target was not met.** Deployment was authorized as a positive-recall-priority experimental trial. The synthetic results do not establish real-room recall or false-event rate. The user subsequently confirmed that it works, but no measured multi-day room trial has concluded.

Technical checks passed: model/config hashes, complete result identity, finite scores, streaming parity, command retention during delayed detection, concurrent streams, silent actual HA wake→STT with an immediately following command, and live microphone flow from both speakers. Silent test transcript: “Apri la finestra.” No intent/action/TTS was executed by that test. OTA, authenticated API reconnection and audio/clock diagnostics were verified on Mansarda. Service showed no restarts during deployment checks.

## Source, restoration and maintenance

- [Runtime, pinned environment, tests and recovery instructions](../voice/wakeword/README.md)
- [Final exact evaluation report](../voice/wakeword/reports/final_report.json)
- [Deployment receipt and user confirmation](../voice/wakeword/reports/deployment.json)
- [HA integration source](../homeassistant/custom_components/nyra_wake)
- [Historical local-model documentation](WAKE_WORDS_LEGACY.md) — superseded for these two installed speakers.

Keep this installed configuration unchanged during the requested room trial. Note speaker, approximate time, background noise/TV, missed wakes, spontaneous wakes and truncated commands. Do not silently retrain, adjust thresholds, restart old Colab jobs, or flash older weights. Alarm handling, arm/disarm chimes, identity and other speaker functions must be preserved in future changes.
