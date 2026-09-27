#!/usr/bin/env bash
set -euo pipefail
SERVICE_NAME=${SERVICE_NAME:-nyra-llm.service}
archive=${1:-}
shift || true
CONFIG_FILE=
FORCE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config-file) CONFIG_FILE=${2:-}; shift 2;;
    --force) FORCE=1; shift;;
    *) exit 2;;
  esac
done
[[ ${EUID} -eq 0 ]] || exit 1
[[ -n $archive && -f $archive && -n $CONFIG_FILE ]] || exit 2
if systemctl is-active --quiet "$SERVICE_NAME"; then echo "stop service before restore" >&2; exit 1; fi
[[ $FORCE -eq 1 || ! -e $CONFIG_FILE ]] || { echo "restore target already exists; use --force" >&2; exit 1; }
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
tar -xzf "$archive" -C "$work"
(cd "$work"; sha256sum -c SHA256SUMS)
test -f "$work/config/llm.env"
install -d -m 0750 "$(dirname "$CONFIG_FILE")"
install -m 0600 "$work/config/llm.env" "$CONFIG_FILE"
