# Wake word: current installed configuration

Soggiorno and Mansarda use the Italian **Ehi Nira** provider on the home server. The current profile started on the evening of 25 November 2026.

Say **“Ehi Nira, che ore sono?”** naturally, without waiting between wake phrase and command. Spaced and joined pronunciations (`ei`, `hei`, `hey`, `ehinira`) are positive cases. **“Nira” alone is excluded.** There is no promise of identical performance for every pronunciation or room.

## Current room profile

The shared service uses `ctc-it-quiet12`. For acoustic scores from 0.85 to below 0.98 it normally requires a letter-alignment cost of 2 or less. If the primary score reaches 0.90 and the lead-in contains zero speech frames, it allows a cost up to 12. The standard branch still requires an acoustic score of 0.98 and a cost up to 14. See the [comparison with the previous profile](../voice/wakeword/README.md#quiet-calls-with-strong-primary-evidence).

Nyra forwards joined commands through `stt.nyra_command_stt` to the same Home Assistant Cloud transcriber. The custom STT entry measures speech after the wake timestamp so speech already buffered during verification counts toward the end of the command. Soggiorno uses aggressive end-of-speech detection. The local-time skill answers direct Italian clock questions from the configured household time zone and closes the conversation.

The service checks the acoustic score, the sounds of the greeting and name, and whether speech was already in progress before the call. This reduces the chance of taking part of a conversation as a wake word. Continuous speech from a TV can also mask an intentional call. The deployed profile and the comparison on synthetic audio are documented in [the wake service guide](../voice/wakeword/README.md#italian-phrase-and-prior-speech-checks).

The preceding 0.98 acoustic-only profile still admitted unintended calls. Its full saved-score evaluation detected 1,953 of 2,835 synthetic positives and produced three activations in 260 minutes of synthetic background. Separate room observations are needed to measure household performance.

## Earlier mitigation profile — 2026-11-25

After repeated morning false wakes, both speakers initially used verifier cutoff **0.8**, raised from **0.2**, through `/opt/nyra-wake/profiles/20261125-less-false-wakes` and the systemd drop-in `20-confirmation-profile.conf`. Model weights, primary detector, VAD, firmware and timing are unchanged; original hashed export remains intact. The baseline metrics below refer to the original 0.2 profile.

Filtering the stored candidate scores at 0.8 gives held-out positives **2,628/2,835 (92.70%)** versus 2,767/2,835, and synthetic ambient events **5/17** over the same 260 minutes (1.15 events/hour). This is score replay, not a new end-to-end room test; it does not establish a 70% reduction at home. Higher false-wake scores were also observed in morning logs, so some spontaneous wakes may remain.

Both live microphone streams/clock states were verified after the service restart. Actual HA synthetic wake→STT passed at probability0.996, with the following command preserved; no household action or TTS was executed. User-voice performance after this change remains unmeasured. [Mitigation receipt](../voice/wakeword/reports/mitigation_20261125.json).

## Audio path and dependencies

ESPHome microphone → Home Assistant `nyra_wake` buffered provider → Wyoming server on the home Intel N100 → openWakeWord primary detector → Italian wav2vec2 V2 INT8 verifier + Silero VAD → existing Nyra Assist pipeline.

The PC and Colab are not needed for operation. The home server, Home Assistant and local network must remain available. The existing downstream STT/LLM/TTS services retain their existing dependencies. Wake processing and its bounded command buffer keep PCM in RAM; this change does not disable any existing downstream voice/identity functionality.

- Service: `nyra-wake.service`, `/opt/nyra-wake`, `192.168.0.16:10401` (trusted LAN; no public exposure or protocol authentication).
- HA provider: `wake_word.nyra_italian_wake`; pipeline: **Nyra - Ehi Nira** (`01m87t35th7w2nk035gqdprs0p`). Original/global default pipelines preserved.
- Primary threshold `.4`, two consecutive 80 ms frames; acoustic verifier `.98` plus phrase and prior-speech checks, 2.8-second window and `.24`-second post-trigger context; VAD `.1` with `.096` seconds minimum speech; candidate refractory 2 seconds.
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

Keep the active mitigation profile stable while measuring the room trial. Note speaker, approximate time, background noise/TV, missed wakes, spontaneous wakes and truncated commands. Do not silently retrain, adjust thresholds, restart old Colab jobs, or flash older weights. Alarm handling, arm/disarm chimes, identity and other speaker functions must be preserved in future changes.
