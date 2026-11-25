# Nyra Italian server wake provider

Installed experimental release: **Italian V2 INT8, Ehi Nira only**, deployed on both Soggiorno and Mansarda on 2026-11-24; user confirmed working on 2026-11-25 and requested an unchanged multi-day trial. See [current behavior and measured limits](../../docs/WAKE_WORDS.md).

## Layout

- `candidate_engine.py`, `cached_frontend.py`, `candidate_wyoming.py`: exact deployed inference/transport sources, compared byte-for-byte with the home service when archived.
- `requirements.lock.txt`: exact deployed Python 3.11 environment. Colab training used separate Python 3.12; do not replace production dependencies with Colab dependencies.
- `nyra-wake.service`: installed service definition, two streams, bounded inference executor, DynamicUser and 1200 MiB memory limit. Adjust the private bind address for another installation.
- `model/config.json`, `model/manifest.json`: immutable exported profile and SHA-256 file inventory. The original config's research/unvalidated metadata records export-time status; use `reports/final_report.json` and `reports/deployment.json` for subsequent evaluation/deployment. Do not edit the hashed config to relabel it successful.
- `reports/`: exact target-machine evaluation and technical deployment evidence. Human confirmation is qualitative, not a measured recognition score.
- `training/`: initial research notebook with outputs removed, primary training/bootstrap and selected Italian V2/export scripts. **Not a consolidated, freshly validated Run All notebook**. Interactive recovery and extra dependencies are preserved in the full Drive archive, not implied to be automated by this historical notebook.
- `evaluate_candidate.py`, `finalize_evaluation.py`, diagnostics and `test_*.py`: frozen evaluation logic and focused regression tests. Finalizer preserves the original recovery paths `/tmp/nyra-italian-benchmark` and `/opt/nyra-wake/recovery`; do not execute it against an incomplete/unrelated run.
- `ha_prepare_candidate.py`, `ha_smoke_candidate.py`, `render_ha_smoke.py`: audited deployment helpers. Prepare **writes** a separate HA entry/pipeline, not a read-only probe. Helpers read the existing `/opt/nyra-router/.env`; credentials are not distributed here. The smoke helper ends at STT and never executes its synthetic command.

## Models and full recovery (not in Git)

Large model binaries, generated WAV/features, personal credentials and raw inference JSONL are excluded from Git. The verifier alone is approximately 357 MB; do not commit it as a normal Git blob. Existing private, hash-verified recovery locations:

1. Home server `/opt/nyra-wake/model/`: complete deployed bundle. Verify **every** entry against `model/manifest.json`, including parity inputs, before starting a restored service.
2. Home server `/opt/nyra-wake/recovery/`: full 6,680-case `results.jsonl`, `plan.json`, `final_report.json`, model manifest, source/checkpoint recovery and testdata archive. `/tmp` is not the durable copy.
3. Google Drive `MyDrive/nyra_openwakeword_it/oww-it-v1-001/nyra_italian_full_recovery_20261124.tar.gz`: 2,936,193,613 bytes, SHA-256 `289d6544406f3d4e89cad36a1153c4a1c2bbecf43bf43a210370f258513f775c`; 23,379 members, each verified. Includes Italian V1/V2/V3 feature/checkpoint/source history and selected FP32/INT8 exports. This is a private prerequisite, not a publicly downloadable release.
4. Candidate ZIP `nyra_italian_candidate_v1.zip`: 361,036,884 bytes, SHA-256 `b09eed35a79fdb0502c5bae8ceb8a1d9dbaf8159913b11b451881e8907f0e01d`.
5. `nyra_final_testdata.tar.gz`: 503,135,284 bytes, SHA-256 `5f6fe14c3304cdc52a94787488abb0e76ee682086abf70e91e05e076de833478`.

Historical Colab: https://colab.research.google.com/drive/18EtC_PdDJ0RabNMzCye5SyR0eq8x7VZ_

The full recovery archive is the authoritative research snapshot; the notebook in Git is the initial notebook, not a copy of every subsequent live Colab cell. A fresh end-to-end retraining/restoration has not been tested from Git alone.

## Restore service and HA integration

This is a recovery procedure, **not an instruction to change the working installation during the trial**.

1. On the N100, copy runtime files into `/opt/nyra-wake`, restore the complete model directory and verify its manifest hashes. Create an isolated Python 3.11 environment at `env`, install `requirements.lock.txt`. The small runtime environment is independent of Router and HA environments.
2. Install the unit into `/etc/systemd/system/nyra-wake.service`, run `systemctl daemon-reload`, then `systemctl enable --now nyra-wake.service`. Check status/journal, resource use and LAN access; do not expose port 10401 publicly.
3. Copy `homeassistant/custom_components/nyra_wake` into `/config/custom_components/nyra_wake`, preserving the separate existing `nyra` integration. HA restart is needed to load a previously unknown custom domain; schedule it around active household functions.
4. Configure `nyra_wake` with host `192.168.0.16`, port `10401`; use a separate Assist pipeline cloned from the existing Nyra pipeline with wake provider **Nyra Italian Wake**, ID `ehi_nira_it`. Preserve STT, conversation agent and TTS selections. The installed HA version was 2026.11.2 with Wyoming 1.10.2; server environment uses Wyoming 1.7.2 and actual interoperability was tested.
5. Select **Nyra - Ehi Nira** on each speaker's primary Assistant selector. Leave the secondary selector/default global pipeline alone. Enable its **Nyra Server Wake Trial** switch and verify `requested=1|paused=0|stream=1|clock=1`. If changing a running pipeline, turn only that trial switch off/on to replace its session.

ESPHome server-mode sources are archived under `esphome/packages/*server-trial.yaml` and `esphome/vendor/*server-trial.yaml`. Configure the device package to include `nyra-speaker-server-trial.yaml`, keeping device-specific secrets, enrollment, alarm indicator and all other functionality. Use `/config/esphome` paths on HA; adapt paths for a local compiler. The deployed Mansarda OTA SHA-256 was `bf99fe7fb8fc6c7fd1ec8a1761edf04f3f0d9d5b3ade67bc71038443b311bd80` (2,244,512 bytes, ESPHome 2026.10.1). This repository does not include a new generic device secret file or require reflashing currently working devices.

The archived server-trial package references the already tracked `esphome/training/v6-004/export_recall_priority` model pairs. Their four files were verified byte-identical to the installed firmware inputs; only the package paths differ from the deployed `/config/esphome/models` paths. Copy that tracked archive too when restoring a firmware build.

The local microWakeWord instances remain part of the firmware audio-clock/lifecycle machinery. Their old labels can remain visible; they are not the normal server-mode recognition profile. `stop_after_detection: false` and existing watchdog/pause/resume logic must be preserved. `RESTORE_DEFAULT_OFF` restores the saved switch state and defaults OFF only when no saved value exists.

## Diagnostics and focused checks

`systemctl status nyra-wake.service` and `journalctl -u nyra-wake.service` report transport/service failures. `systemctl kill -s SIGUSR1 --kill-who=main nyra-wake.service` requests bounded numeric score snapshots after the service is initialized; snapshots do not contain PCM or transcripts. Verify both engines' processed-audio counters advance. Do not infer successful human recognition from counters alone.

From this directory, use a separate test environment with `pip install -r requirements-test.txt` (adds SciPy 1.15.3 to the pinned runtime dependencies). Do not add test dependencies to the running production service:

```sh
python -m unittest test_audio_buffer test_buffered_stream test_candidate_wyoming test_candidate_history test_evaluation_metrics test_finalizer_identity
```

Tests use synthetic/mocked audio and local sockets, without physical device changes. Model parity/concurrency diagnostics additionally require the complete private model bundle and testdata. HA integration files can be syntax-checked without installing Home Assistant, but that does not replace the actual HA wake→STT test already recorded in `reports/ha_smoke_result.json`.

Upstream provenance: openWakeWord `368c03716d1e92591906a84949bc477f3a834455`; pyopen-wakeword `6bc5c5f5c9c71e46a723b6c9277b1d50f2ba13fd`; Italian encoder `jonatasgrosman/wav2vec2-large-xlsr-53-italian` revision `dab04a3e00d8326052f3fb22a6ff276b822f6131` (Apache-2.0); Silero source `bfa5f8cef40abb5de2bd4a2f4c3f22778172dfec`. Preserve upstream license requirements when redistributing model bundles.

## Current false-wake mitigation (2026-11-25)

The active service uses `profiles/20261125-less-false-wakes`, verifier cutoff0.8; the original `model` export remains immutable at0.2. See the current wake-word guide for recall/false-event tradeoffs. To reconstruct this profile, copy its tracked config/manifest into the same relative directory under `/opt/nyra-wake`; for each manifest entry except `config.json`, restore the matching original model file or create a symlink to `/opt/nyra-wake/model/<name>`. Verify every manifest SHA. Install the tracked `20-confirmation-profile.conf` into `/etc/systemd/system/nyra-wake.service.d/`, then reload/restart the service. This separate profile/drop-in preserves the original model bundle and does not require new speaker firmware. No new training or complete dataset generation was performed.

## Strict confirmation supersedes 0.8

As of 2026-11-25 12:54 Europe/Rome the active profile is `profiles/20261125-strict98`, cutoff0.98. Restore using that directory and its drop-in, following the same symlink/manifest procedure above. The earlier0.8 profile is historical and preserved. User confirmed all six recent wakes were false; their scores would all be rejected at0.98. Saved-score positive recall drops to68.89%; human recall and future room false-wake rate remain unmeasured.
