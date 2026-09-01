# microWakeWord training notebooks

This directory stores the Google Colab notebooks used to train Nyra's local ESPHome `micro_wake_word` models.

Canonical notebooks:

- `MicroWakeWord_Nyra_IT_V3_FULL_66GB.ipynb` — Italian `nyra_it`, real + synthetic positives.
- `MicroWakeWord_Nyra_EN_V1_SYNTHETIC_66GB.ipynb` — English `nyra_en`, synthetic-only.

See [`../../docs/WAKE_WORDS.md`](../../docs/WAKE_WORDS.md) before modifying or running them.

The notebooks are intentionally committed as reproducible training artifacts. Generated datasets, temporary Colab data, Google Drive work directories, and raw personal recordings are not repository assets.
