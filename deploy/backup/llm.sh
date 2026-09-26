#!/usr/bin/env bash
set -euo pipefail
CONFIG_FILE=${CONFIG_FILE:-/etc/nyra/llm.env}
BACKUP_DIR=${BACKUP_DIR:-/var/backups/nyra-llm}
[[ ${EUID} -eq 0 ]] || exit 1
test -f "$CONFIG_FILE"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
output=${1:-$BACKUP_DIR/nyra-llm-$timestamp.tar.gz}
install -d -m 0700 "$(dirname "$output")"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/config"
cp "$CONFIG_FILE" "$work/config/llm.env"
(cd "$work"; sha256sum config/llm.env >SHA256SUMS; tar -czf "$output" config SHA256SUMS)
chmod 0600 "$output"
sha256sum "$output"
echo "$output"
