#!/usr/bin/env bash
set -euo pipefail

DATA_DIR=${DATA_DIR:-/var/lib/nyra-memory}
SERVICE_USER=${SERVICE_USER:-nyra-memory}
archive=${1:-}

if [[ ${EUID} -ne 0 ]]; then
  echo "memory restore must run as root" >&2
  exit 1
fi
if [[ -z $archive || ! -f $archive ]]; then
  echo "usage: deploy/restore/memory.sh BACKUP.tar.gz" >&2
  exit 2
fi
if systemctl is-active --quiet nyra-memory; then
  echo "stop nyra-memory before restore" >&2
  exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
while IFS= read -r member; do
  case $member in
    memory.sqlite3|SHA256SUMS) ;;
    *) echo "unexpected archive member: $member" >&2; exit 1 ;;
  esac
done < <(tar -tzf "$archive")
tar -xzf "$archive" -C "$work"
(
  cd "$work"
  sha256sum -c SHA256SUMS
  sqlite3 memory.sqlite3 "PRAGMA integrity_check" | grep -qx ok
)
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$DATA_DIR"
install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0640 \
  "$work/memory.sqlite3" "$DATA_DIR/memory.sqlite3.new"
mv "$DATA_DIR/memory.sqlite3.new" "$DATA_DIR/memory.sqlite3"
chown "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR/memory.sqlite3"
echo "Memory restored; start nyra-memory and run deploy/verify/memory.sh"
