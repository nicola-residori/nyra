#!/bin/bash
# macOS Bash 3.2 runner. Isolated clone + software verification; no deployment.
set -euo pipefail
RUNNER_DIR="$(cd "$(dirname "$0")" && pwd)"
NYRA_REVISION="${NYRA_VERIFY_REVISION:-}"
if [ -z "$NYRA_REVISION" ] && [ -f "$RUNNER_DIR/REVISION" ]; then
  NYRA_REVISION="$(cat "$RUNNER_DIR/REVISION")"
fi
if [ -n "$NYRA_REVISION" ] && ! [[ "$NYRA_REVISION" =~ ^[0-9a-f]{40}$ ]]; then
  printf '%s\n' 'REVISION must contain a full Git commit hash.' >&2
  exit 2
fi
PYTHON_CHOICE=''
for CANDIDATE in python3.13 python3.12 python3.11 python3; do
  if command -v "$CANDIDATE" >/dev/null 2>&1 && "$CANDIDATE" -c 'import sys; assert sys.version_info >= (3, 11)' >/dev/null 2>&1; then
    PYTHON_CHOICE="$CANDIDATE"
    break
  fi
done
if [ -z "$PYTHON_CHOICE" ]; then
  printf '%s\n' 'Install Python 3.11 or newer, then run this file again.' >&2
  exit 2
fi
command -v git >/dev/null 2>&1
command -v c++ >/dev/null 2>&1 || { printf '%s\n' 'Install Xcode command-line tools for the native firmware tests.' >&2; exit 2; }
NYRA_VERIFY_DIR="$(mktemp -d "${TMPDIR:-/tmp}/nyra-voice-alerts.XXXXXX")"
printf 'Verification folder: %s\n' "$NYRA_VERIFY_DIR"
git clone --single-branch --branch feat/persistent-voice-alerts https://github.com/nicola-residori/nyra.git "$NYRA_VERIFY_DIR/nyra"
cd "$NYRA_VERIFY_DIR/nyra"
if [ -n "$NYRA_REVISION" ]; then
  git checkout --detach "$NYRA_REVISION"
fi
"$PYTHON_CHOICE" -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
PYTHON_BIN=.venv/bin/python bash deploy/verify/voice-alerts.sh
printf '\n%s\n' 'Checks passed. No firmware upload, service deployment or main merge was performed.'
printf 'Physical validation guide: %s/docs/voice-alerts.md\n' "$NYRA_VERIFY_DIR/nyra"
