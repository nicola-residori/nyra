#!/usr/bin/env bash
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/nyra-memory}
DATA_DIR=${DATA_DIR:-/var/lib/nyra-memory}
SERVICE_USER=${SERVICE_USER:-nyra-memory}
SERVICE_NAME=${SERVICE_NAME:-nyra-memory.service}
BASE_URL=${BASE_URL:-http://127.0.0.1:8090}
MODE=verify
SNAPSHOT_FILE=

usage() {
  cat <<'EOF'
Usage:
  deploy/verify/memory.sh
  deploy/verify/memory.sh --snapshot FILE
  deploy/verify/memory.sh --verify-snapshot FILE

Create a snapshot before reboot and compare it after reboot. The snapshot
covers schema, operational/semantic/tombstone counts, and the model cache.
EOF
}

case ${1:-} in
  "") ;;
  --snapshot|--verify-snapshot)
    MODE=${1#--}
    SNAPSHOT_FILE=${2:-}
    if [[ -z $SNAPSHOT_FILE || $# -ne 2 ]]; then usage >&2; exit 2; fi
    ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

if [[ ${EUID} -ne 0 ]]; then
  echo "memory verification must run as root" >&2
  exit 1
fi

id "$SERVICE_USER" >/dev/null
test -f "$APP_DIR/memory/app.py"
test -d "$APP_DIR/shared"
test -x "$APP_DIR/.venv/bin/python"
test -d "$DATA_DIR/models/huggingface"
test -s "$DATA_DIR/memory.sqlite3"
test "$(stat -c '%U:%G' "$DATA_DIR")" = "$SERVICE_USER:$SERVICE_USER"

systemctl is-enabled --quiet "$SERVICE_NAME"
systemctl is-active --quiet "$SERVICE_NAME"
test "$(systemctl show "$SERVICE_NAME" -p User --value)" = "$SERVICE_USER"
test "$(systemctl show "$SERVICE_NAME" -p Group --value)" = "$SERVICE_USER"
test "$(systemctl show "$SERVICE_NAME" -p WorkingDirectory --value)" = "$APP_DIR"

"$APP_DIR/.venv/bin/python" -c \
  "import fastapi, sentence_transformers, uvicorn; from memory.app import create_app"
sqlite3 "$DATA_DIR/memory.sqlite3" "PRAGMA integrity_check" | grep -qx ok

health_json=$(curl --silent --show-error --fail "$BASE_URL/health")
ready_json=$(curl --silent --show-error --fail "$BASE_URL/ready")
HEALTH_JSON=$health_json READY_JSON=$ready_json "$APP_DIR/.venv/bin/python" - <<'PY'
import json
import os

health = json.loads(os.environ["HEALTH_JSON"])
ready = json.loads(os.environ["READY_JSON"])
assert health["service"] == "nyra-memory"
assert health["status"] == "healthy"
assert ready["ready"] is True
assert ready["storage"] == "initialized"
assert ready["embedding"] == "loaded"
assert ready["embedding_model"]
PY

create_snapshot() {
  DATA_DIR="$DATA_DIR" READY_JSON="$ready_json" "$APP_DIR/.venv/bin/python" - <<'PY'
import json
import os
import sqlite3
from pathlib import Path

root = Path(os.environ["DATA_DIR"])
database = root / "memory.sqlite3"
with sqlite3.connect(database) as connection:
    tables = sorted(row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ))
    counts = {
        table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        for table in ("operational_entries", "semantic_memories", "semantic_tombstones")
    }
ready = json.loads(os.environ["READY_JSON"])
model_files = sum(1 for path in (root / "models").rglob("*") if path.is_file())
assert model_files > 0
print(json.dumps({
    "tables": tables,
    "counts": counts,
    "embedding_model": ready["embedding_model"],
    "model_cached": True,
}, sort_keys=True, separators=(",", ":")))
PY
}

case $MODE in
  snapshot)
    install -m 0600 /dev/null "$SNAPSHOT_FILE"
    create_snapshot >"$SNAPSHOT_FILE"
    echo "Memory persistence snapshot saved to $SNAPSHOT_FILE"
    ;;
  verify-snapshot)
    test -s "$SNAPSHOT_FILE"
    current_snapshot=$(mktemp)
    trap 'rm -f "$current_snapshot"' EXIT
    create_snapshot >"$current_snapshot"
    cmp --silent "$SNAPSHOT_FILE" "$current_snapshot"
    echo "Memory persisted state matches $SNAPSHOT_FILE"
    ;;
esac

echo "Memory deployment verification passed"
