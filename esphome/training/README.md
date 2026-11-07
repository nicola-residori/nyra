# microWakeWord training notebooks

This directory stores the Google Colab notebooks used to train Nyra's local ESPHome `micro_wake_word` models.

Canonical notebooks:

- `MicroWakeWord_Nyra_IT_V3_FULL_66GB.ipynb` — Italian `nyra_it`, real + synthetic positives.
- `MicroWakeWord_Nyra_EN_V1_SYNTHETIC_66GB.ipynb` — English `nyra_en`, synthetic-only.

See [`../../docs/WAKE_WORDS.md`](../../docs/WAKE_WORDS.md) before modifying or running them.

The notebooks are intentionally committed as reproducible training artifacts. Generated datasets, temporary Colab data, Google Drive work directories, and raw personal recordings are not repository assets.

## Italian V6 final run (2026-11-06)

- [Final recovery and export notebook](MicroWakeWord_Nyra_IT_V6_FINAL_RECOVERY_EXPORT.ipynb): consolidated final workflow for the completed `nyra-it-v6-004-continuous` run. Restores the approved worker, completed weights and synthetic WAV archive from Drive; evaluates and exports without restarting synthesis/training. Requires that private Drive backup; weights/dataset are not included in Git.
- [Original complete training notebook](MicroWakeWord_Nyra_IT_V6_CONTINUOUS_AUTO_66GB.ipynb): historical starting pipeline, retained for provenance. It does not incorporate every interactive recovery fix; do not run all its cells to resume the completed run. The exact approved worker including the duration retry fix is archived in `v6-004/nyra_v6_worker.py`.
- [Installed export](v6-004/export_recall_priority): both TFLite files, ESPHome manifests, model hashes and synthetic evaluation reports.
- [Deployment receipt](v6-004/DEPLOYMENT_2026-11-06.json): successful sequential OTA and 65-second runtime verification on both speakers.

The final profile prioritizes positive recall, as requested. It does **not** pass the original 0.5 false-positive/hour gate. Synthetic test recall is approximately 99% for each model; real-room/human recognition and audible alarm behavior have not been tested. Model false-positive rates are separate, not a combined device rate. Tensor arena size is an estimate. The consolidated notebook was structurally/syntax validated locally; it has not been rerun end-to-end as a new run. Original Colab: https://colab.research.google.com/drive/162cYXStHB3FG2fHJi-Dqr9MgEGUDvY31
