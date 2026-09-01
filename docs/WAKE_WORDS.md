# Nyra Wake Words

Nyra uses ESPHome `micro_wake_word` models that execute locally on the ESP32 speaker.

The project defines two canonical language-specific Nyra wake words:

| Model ID | Visible wake word | Target pronunciation | Training profile |
| --- | --- | --- | --- |
| `nyra_it` | Nyra | Italian “Nì-ra” | real + synthetic |
| `nyra_en` | Nyra | English “NYE-ruh” | synthetic-only |

`nyra_it` is the first validated runtime model. `nyra_en` is the second canonical model and becomes part of the default speaker model set once its exported `.tflite` and manifest are committed.

The two models intentionally share the human-facing word **Nyra** but are trained separately because pronunciation and acoustic distributions differ by language.

## Repository layout

```text
esphome/
├── models/
│   ├── nyra_it.json
│   ├── nyra_it.tflite
│   ├── nyra_en.json
│   └── nyra_en.tflite
├── packages/
│   └── nyra-speaker.yaml
└── training/
    ├── MicroWakeWord_Nyra_IT_V3_FULL_66GB.ipynb
    └── MicroWakeWord_Nyra_EN_V1_SYNTHETIC_66GB.ipynb
```

The exported `.json` manifest references the matching `.tflite` file. Both files must be copied together.

## Training environment

The supplied notebooks are designed for **Google Colab** and were developed/tested with an **NVIDIA L4 GPU**.

The target runtime profile is approximately:

- 113 GB local disk
- about 66 GB initially free
- about 52 GB system RAM
- NVIDIA L4 GPU

The notebooks actively manage disk usage and delete source WAV data after mmap features have been generated.

### Select the Colab runtime

Open the notebook in Google Colab, then choose:

```text
Runtime
  -> Change runtime type
  -> Hardware accelerator: GPU
  -> GPU type: L4
```

An L4 is the recommended and known-good configuration for these notebooks. Other GPUs may work, but disk/RAM/GPU behavior has not been validated by the Nyra project and may require tuning.

The notebooks mount Google Drive and use it for persistent inputs and outputs. Colab's local runtime disk is temporary.

## Italian workflow: real + synthetic

Use:

```text
esphome/training/MicroWakeWord_Nyra_IT_V3_FULL_66GB.ipynb
```

This notebook trains `nyra_it` for the Italian pronunciation **Nì-ra**.

It combines:

- real positive recordings supplied in `nyra_it_real_samples.zip`
- synthetic positive samples generated with Italian Piper voices
- synthetic hard negatives chosen to resemble the wake word
- standard negative/background feature datasets used by the microWakeWord training pipeline

Real and synthetic positives are kept as separate feature sources so a small set of real recordings is not statistically lost inside thousands of generated examples.

### Real recordings

Place the real samples in a ZIP named by `REAL_SAMPLES_ZIP_NAME`.

The default is:

```python
REAL_SAMPLES_ZIP_NAME = "nyra_it_real_samples.zip"
EXPECTED_REAL_SAMPLES = 30
```

Folder names and WAV filenames inside the ZIP do not matter. Every `.wav` found in the archive is treated as a positive sample.

For another wake word, record multiple clean examples from the intended users and preferably vary:

- distance from the microphone
- speaking volume
- room acoustics
- cadence
- speaker
- microphone angle

Do not deliberately include wrong pronunciations as positives.

### Parameters to customize

The principal configuration fields are:

```python
WAKE_WORD = "Nyra"
PRONUNCIATION = "Nira"
OUTPUT_NAME = "nyra_it"

REAL_SAMPLES_ZIP_NAME = "nyra_it_real_samples.zip"
EXPECTED_REAL_SAMPLES = 30
```

For a different word:

- `WAKE_WORD`: the human-facing phrase.
- `PRONUNCIATION`: text that guides the synthetic Italian voices toward the intended sound.
- `OUTPUT_NAME`: technical model identifier and exported filename stem.
- `REAL_SAMPLES_ZIP_NAME`: your real-positive archive.
- `EXPECTED_REAL_SAMPLES`: expected number of real WAVs.

Also review `CONFUSABLE_WORDS`. These are deliberately similar **negative** examples and are important for teaching the model what must *not* trigger it.

For example, a custom word should have confusables that are close in syllable count, vowels, consonants, stress, or normal phrases likely to occur in conversation.

### Preview before full generation

The Italian notebook generates a small synthetic preview before the expensive full generation/training stage.

Listen to the preview. If the synthetic pronunciation does not match the intended wake word, stop and fix `PRONUNCIATION` and/or the generator configuration before continuing.

Synthetic data with the wrong pronunciation teaches the wrong model.

## English workflow: synthetic-only

Use:

```text
esphome/training/MicroWakeWord_Nyra_EN_V1_SYNTHETIC_66GB.ipynb
```

This notebook trains `nyra_en` without real recordings.

It uses the English **LibriTTS-R multi-speaker Piper sample generator** and produces a large, diverse synthetic positive set.

The default target is English **NYE-ruh**, approximately `/ˈnaɪrə/`.

### Do not let TTS guess invented names

The important configuration value is:

```python
WAKE_WORD_PHONEMES = "nˈaɪɹə"
```

The notebook passes phonemes to the sample generator so the English TTS model does not have to guess how an invented spelling such as `Nyra` should sound.

For another invented/custom wake word, determine the pronunciation you actually want and update the phoneme sequence accordingly.

The visible name and technical ID are configured separately:

```python
WAKE_WORD = "Nyra"
OUTPUT_NAME = "nyra_en"
```

### Preview gate

The English notebook creates preview samples first and lets you listen to them directly in Colab.

The default gate is:

```python
PREVIEW_SAMPLES = 24
PREVIEW_APPROVAL_TEXT = "OK"
```

Full positive generation cannot continue until the preview is explicitly approved.

This gate should not be bypassed. For a custom wake word, the preview is where you verify that your phoneme sequence and synthetic voices produce the intended pronunciation.

### Confusable phonemes

English hard negatives are expressed as phrase/phoneme pairs:

```python
CONFUSABLE_PHONEMES = [
    ("Myra", "mˈaɪɹə"),
    ("Lyra", "lˈaɪɹə"),
    ...
]
```

Replace these with words and short expressions that could realistically be confused with your new wake word.

They are negative examples: they should sound close without being the desired trigger.

## Parameters that normally should not be changed first

The supplied notebooks also expose parameters such as:

- positive sample counts
- repetitions / feature sampling weights
- probability cutoff
- sliding-window size
- tensor-arena size
- disk reserve
- training hyperparameters
- feature-generation settings

These values affect memory use, training balance, false accepts, false rejects, runtime performance, and ESP32 compatibility.

When creating a new wake word, first customize:

1. wake-word text
2. intended pronunciation or phonemes
3. model/output ID
4. language / TTS source
5. real-positive archive if using the hybrid notebook
6. confusable negatives

Keep the known-good training and manifest values initially. Tune thresholds only after testing the exported model on the actual speaker.

## General custom wake-word procedure

A practical workflow is:

```text
choose the wake word
        |
        v
define exactly how it must sound
        |
        +--> Italian/hybrid: pronunciation text + real WAVs
        |
        +--> English/synthetic: explicit phonemes
        |
        v
choose realistic confusable negatives
        |
        v
run preview in Colab on L4
        |
        v
listen critically
        |
        +--> wrong pronunciation -> fix config and regenerate preview
        |
        v
approve preview
        |
        v
generate full dataset
        |
        v
extract features
        |
        v
train
        |
        v
export .tflite + .json
        |
        v
test on the real ESP32 speaker
        |
        v
tune thresholds only if needed
```

## Exported model files

A successful notebook run exports:

```text
<output_name>.tflite
<output_name>.json
```

For example:

```text
nyra_it.tflite
nyra_it.json

nyra_en.tflite
nyra_en.json
```

Copy both files into:

```text
esphome/models/
```

The manifest's `model` field must reference the matching TFLite filename.

ESPHome currently expects a microWakeWord manifest schema supported by the installed ESPHome version. If a trainer exports a newer/incompatible manifest schema, adapt the manifest to the schema accepted by the project's ESPHome baseline without changing the actual trained model.

## Add the model to the Nyra speaker package

Nyra loads repository-managed local models from Home Assistant's ESPHome configuration directory.

A local model entry has the form:

```yaml
micro_wake_word:
  models:
    - model: /config/esphome/models/my_wake_word.json
      id: my_wake_word
```

The Nyra package is layered on top of a pinned Waveshare base package. Do **not** redefine upstream model IDs already supplied by that package: ESPHome will reject duplicate IDs.

For the canonical Nyra pair, the intended local additions are:

```yaml
micro_wake_word:
  models:
    - model: /config/esphome/models/nyra_it.json
      id: nyra_it
    - model: /config/esphome/models/nyra_en.json
      id: nyra_en
```

The runtime package should reference `nyra_en` only once the matching `nyra_en.json` and `nyra_en.tflite` artifacts exist.

## Deploy models to Home Assistant

Copy the model files and shared package into the ESPHome directory used by Home Assistant:

```text
/config/esphome/models/
 /config/esphome/packages/nyra-speaker.yaml
```

Then validate the target speaker configuration in **ESPHome Device Builder** before installing it.

A valid configuration should list every intended wake-word model exactly once.

## First-device testing

Do not judge a model only by training metrics. Test on the actual Waveshare speaker.

Evaluate at least:

- intended pronunciation at normal distance
- quiet and noisy rooms
- different speaking volumes
- several users where possible
- television/conversation false triggers
- words chosen as confusables
- repeated wake/sleep cycles

Tune `probability_cutoff` and `sliding_window_size` only after collecting real device behavior. Increasing strictness can reduce false accepts while also increasing missed wake words; lowering it has the opposite trade-off.

## Nyra default policy

Nyra's intended default local wake-word pair is:

```text
nyra_it
nyra_en
```

They are two acoustic models for the same assistant name, not aliases of one model.

This keeps pronunciation-specific training explicit while allowing the speaker to respond naturally to both Italian and English users.
