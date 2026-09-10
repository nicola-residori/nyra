#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME=${SERVICE_NAME:-nyra-skills.service}

usage() {
  cat <<'EOF'
Usage:
  deploy/restore/skills.sh BACKUP.tar.gz --data-dir DIR --config-file FILE [--force]

The target paths are mandatory. Existing job DB/config are never overwritten
unless --force is explicitly supplied. Stop nyra-skills before restore.
EOF
}

archive=${1:-}
shift || true

DATA_DIR=
CONFIG_FILE=
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --data-dir)
      DATA_DIR=${2:-}
      shift 2
      ;;
    --config-file)
      CONFIG_FILE=${2:-}
      shift 2
      ;;
    --force)
      FORCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ${EUID} -ne 0 ]]; then
  echo "skills restore must run as root" >&2
  exit 1
fi
if [[ -z $archive || ! -f $archive || -z $DATA_DIR || -z $CONFIG_FILE ]]; then
  usage >&2
  exit 2
fi
if systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "stop $SERVICE_NAME before restore" >&2
  exit 1
fi
if [[ $FORCE -ne 1 && ( -e $DATA_DIR/jobs.sqlite3 || -e $CONFIG_FILE ) ]]; then
  echo "restore target already exists; rerun with --force after inspection" >&2
  exit 1
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

while IFS= read -r member; do
  case "$member" in
    data/|config/|data/jobs.sqlite3|config/skills.env|SHA256SUMS) ;;
    *) echo "unexpected archive member: $member" >&2; exit 1 ;;
  esac
done < <(tar -tzf "$archive")

tar -xzf "$archive" -C "$work"
(
  cd "$work"
  sha256sum -c SHA256SUMS
)

if [[ -f $work/data/jobs.sqlite3 ]]; then
  sqlite3 "$work/data/jobs.sqlite3" "PRAGMA integrity_check" | grep -qx ok
fi
test -f "$work/config/skills.env"

install -d -o root -g root -m 0750 "$DATA_DIR"
install -d -o root -g root -m 0750 "$(dirname "$CONFIG_FILE")"

if [[ -f $work/data/jobs.sqlite3 ]]; then
  install -o root -g root -m 0640 \
    "$work/data/jobs.sqlite3" "$DATA_DIR/jobs.sqlite3.new"
  mv "$DATA_DIR/jobs.sqlite3.new" "$DATA_DIR/jobs.sqlite3"
fi

install -o root -g root -m 0600 \
  "$work/config/skills.env" "$CONFIG_FILE.new"
mv "$CONFIG_FILE.new" "$CONFIG_FILE"

echo "Skills restored; start $SERVICE_NAME and run deploy/verify/skills.sh"
