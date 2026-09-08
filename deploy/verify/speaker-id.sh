#!/usr/bin/env bash
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/nyra-speaker-id}
DATA_DIR=${DATA_DIR:-/var/lib/nyra-speaker-id}
SERVICE_USER=${SERVICE_USER:-nyra-speaker-id}
SERVICE_NAME=${SERVICE_NAME:-nyra-speaker-id.service}
BASE_URL=${BASE_URL:-http://127.0.0.1:8090}
MODE=verify
SNAPSHOT_FILE=

usage() {
  cat <<'EOF'
Usage:
  deploy/verify/speaker-id.sh
  deploy/verify/speaker-id.sh --snapshot FILE
  deploy/verify/speaker-id.sh --verify-snapshot FILE

Run --snapshot before reboot and --verify-snapshot after reboot. The comparison
covers runtime threshold/margin, profile/enrollment/wake-word counts, schema,
and the persistent model cache.
EOF
}

case ${1:-} in
  "") ;;
  --snapshot|--verify-snapshot)
    MODE=${1#--}
    SNAPSHOT_FILE=${2:-}
    if [[ -z $SNAPSHOT_FILE || $# -ne 2 ]]; then
      usage >&2
      exit 2
    fi
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

if [[ ${EUID} -ne 0 ]]; then
  echo "speaker-id verification must run as root" >&2
  exit 1
fi

id "$SERVICE_USER" >/dev/null
test -d "$APP_DIR"
test -f "$APP_DIR/app.py"
test -x "$APP_DIR/.venv/bin/python"
test -d "$APP_DIR/shared"
test -d "$DATA_DIR"
test -d "$DATA_DIR/audio"
test -d "$DATA_DIR/models"
test -d "$DATA_DIR/models/huggingface"
test -s "$DATA_DIR/speaker-id.sqlite3"
test -s "$DATA_DIR/speaker_id.sqlite3"
test "$(stat -c '%U:%G' "$DATA_DIR")" = "$SERVICE_USER:$SERVICE_USER"

systemctl is-enabled --quiet "$SERVICE_NAME"
systemctl is-active --quiet "$SERVICE_NAME"
test "$(systemctl show "$SERVICE_NAME" -p User --value)" = "$SERVICE_USER"
test "$(systemctl show "$SERVICE_NAME" -p Group --value)" = "$SERVICE_USER"
test "$(systemctl show "$SERVICE_NAME" -p WorkingDirectory --value)" = "$APP_DIR"

"$APP_DIR/.venv/bin/python" -c \
  "import fastapi, speechbrain, torch, torchaudio, uvicorn"

health_json=$(curl --silent --show-error --fail "$BASE_URL/health")
ready_json=$(curl --silent --show-error --fail "$BASE_URL/ready")
HEALTH_JSON=$health_json READY_JSON=$ready_json "$APP_DIR/.venv/bin/python" - <<'PY'
import json
import os

health = json.loads(os.environ["HEALTH_JSON"])
ready = json.loads(os.environ["READY_JSON"])
assert health["service"] == "nyra-speaker-id"
assert health["status"] == "healthy"
assert ready == {"ready": True, "storage": "initialized", "model": "loaded"}
PY

runuser -u "$SERVICE_USER" -- env \
  HOME="$DATA_DIR" \
  HF_HOME="$DATA_DIR/models/huggingface" \
  PYTHONPATH="$APP_DIR" \
  bash -c 'cd "$1" && exec "$2" -c "$3"' _ \
  "$APP_DIR" "$APP_DIR/.venv/bin/python" \
  "from embeddings import SpeechBrainECAPAEngine; SpeechBrainECAPAEngine(savedir='$DATA_DIR/models/ecapa').validate()"

create_snapshot() {
  DATA_DIR="$DATA_DIR" "$APP_DIR/.venv/bin/python" - <<'PY'
import json
import os
import sqlite3
from pathlib import Path

root = Path(os.environ["DATA_DIR"])
config_database = root / "speaker-id.sqlite3"
biometric_database = root / "speaker_id.sqlite3"
with sqlite3.connect(config_database) as connection:
    config_tables = sorted(row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ))
    config = connection.execute(
        "SELECT threshold, margin, revision FROM runtime_config WHERE key='identification'"
    ).fetchone()

with sqlite3.connect(biometric_database) as connection:
    biometric_tables = sorted(row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ))
    counts = {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("speaker_profiles", "enrollment_samples", "wake_word_samples")
    }

model_files = sum(1 for path in (root / "models").rglob("*") if path.is_file())
assert config is not None
assert model_files > 0
print(json.dumps({
    "schema_tables": {
        "speaker-id.sqlite3": config_tables,
        "speaker_id.sqlite3": biometric_tables,
    },
    "identification": {
        "threshold": config[0], "margin": config[1], "revision": config[2]
    },
    "counts": counts,
    "model_cached": model_files > 0,
}, sort_keys=True, separators=(",", ":")))
PY
}

case $MODE in
  snapshot)
    install -m 0600 /dev/null "$SNAPSHOT_FILE"
    create_snapshot >"$SNAPSHOT_FILE"
    echo "Speaker-ID persistence snapshot saved to $SNAPSHOT_FILE"
    ;;
  verify-snapshot)
    test -s "$SNAPSHOT_FILE"
    current_snapshot=$(mktemp)
    trap 'rm -f "$current_snapshot"' EXIT
    create_snapshot >"$current_snapshot"
    cmp --silent "$SNAPSHOT_FILE" "$current_snapshot"
    echo "Speaker-ID persisted state matches $SNAPSHOT_FILE"
    ;;
esac

echo "Speaker-ID deployment verification passed"
