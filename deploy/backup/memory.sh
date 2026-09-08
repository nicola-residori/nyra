#!/usr/bin/env bash
set -euo pipefail

DATA_DIR=${DATA_DIR:-/var/lib/nyra-memory}
BACKUP_DIR=${BACKUP_DIR:-/var/backups/nyra-memory}
DATABASE=${DATABASE:-$DATA_DIR/memory.sqlite3}
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
output=${1:-$BACKUP_DIR/nyra-memory-$timestamp.tar.gz}

if [[ ${EUID} -ne 0 ]]; then
  echo "memory backup must run as root" >&2
  exit 1
fi

test -s "$DATABASE"
install -d -m 0700 "$(dirname "$output")"
output_dir=$(cd "$(dirname "$output")" && pwd)
output="$output_dir/$(basename "$output")"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
sqlite3 "$DATABASE" ".backup '$work/memory.sqlite3'"
sqlite3 "$work/memory.sqlite3" "PRAGMA integrity_check" | grep -qx ok
(
  cd "$work"
  sha256sum memory.sqlite3 >SHA256SUMS
  tar -czf "$output" memory.sqlite3 SHA256SUMS
)
chmod 0600 "$output"
echo "$output"
