#!/usr/bin/env bash
set -euo pipefail

DATA_DIR=${DATA_DIR:-/var/lib/nyra-skills}
CONFIG_FILE=${CONFIG_FILE:-/etc/nyra/skills.env}
BACKUP_DIR=${BACKUP_DIR:-/var/backups/nyra-skills}
DATABASE=${DATABASE:-$DATA_DIR/jobs.sqlite3}
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
output=${1:-$BACKUP_DIR/nyra-skills-$timestamp.tar.gz}

if [[ ${EUID} -ne 0 ]]; then
  echo "skills backup must run as root" >&2
  exit 1
fi

test -f "$CONFIG_FILE"
install -d -m 0700 "$(dirname "$output")"
output_dir=$(cd "$(dirname "$output")" && pwd)
output="$output_dir/$(basename "$output")"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

mkdir -p "$work/data" "$work/config"

if [[ -s $DATABASE ]]; then
  sqlite3 "$DATABASE" ".backup '$work/data/jobs.sqlite3'"
  sqlite3 "$work/data/jobs.sqlite3" "PRAGMA integrity_check" | grep -qx ok
fi
cp "$CONFIG_FILE" "$work/config/skills.env"

(
  cd "$work"
  find data config -type f -print0 | sort -z | xargs -0 sha256sum >SHA256SUMS
  tar -czf "$output" data config SHA256SUMS
)

chmod 0600 "$output"
sha256sum "$output"
echo "$output"
