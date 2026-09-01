#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:-$PWD}"
downloads="${2:-$HOME/Downloads}"
dest="$repo_root/esphome/training"

mkdir -p "$dest"

copy_one() {
  local canonical="$1"
  shift
  local candidate
  for candidate in "$@"; do
    if [[ -f "$downloads/$candidate" ]]; then
      cp "$downloads/$candidate" "$dest/$canonical"
      echo "Imported $candidate -> esphome/training/$canonical"
      return 0
    fi
  done
  echo "ERROR: cannot find $canonical in $downloads" >&2
  echo "Looked for:" >&2
  printf '  - %s\n' "$@" >&2
  return 1
}

copy_one \
  "MicroWakeWord_Nyra_IT_V3_FULL_66GB.ipynb" \
  "MicroWakeWord_Nyra_IT_V3_FULL_66GB(1).ipynb" \
  "MicroWakeWord_Nyra_IT_V3_FULL_66GB.ipynb"

copy_one \
  "MicroWakeWord_Nyra_EN_V1_SYNTHETIC_66GB.ipynb" \
  "MicroWakeWord_Nyra_EN_V1_SYNTHETIC_66GB(1).ipynb" \
  "MicroWakeWord_Nyra_EN_V1_SYNTHETIC_66GB.ipynb"

echo "Wake-word notebooks imported."
