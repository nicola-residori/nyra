#!/usr/bin/env bash
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/nyra-skills}
DATA_DIR=${DATA_DIR:-/var/lib/nyra-skills}
CONFIG_FILE=${CONFIG_FILE:-/etc/nyra/skills.env}
SERVICE_NAME=${SERVICE_NAME:-nyra-skills.service}
BASE_URL=${BASE_URL:-http://127.0.0.1:8090}

if [[ ${EUID} -ne 0 ]]; then
  echo "skills verification must run as root" >&2
  exit 1
fi

test -f "$APP_DIR/skills/app.py"
test -d "$APP_DIR/shared"
test -x "$APP_DIR/.venv/bin/python"
test -d "$DATA_DIR"
test -f "$CONFIG_FILE"
test -w "$DATA_DIR"

systemctl is-enabled --quiet "$SERVICE_NAME"
systemctl is-active --quiet "$SERVICE_NAME"
test "$(systemctl show "$SERVICE_NAME" -p User --value)" = "root"
test "$(systemctl show "$SERVICE_NAME" -p WorkingDirectory --value)" = "$APP_DIR"

"$APP_DIR/.venv/bin/python" -c \
  "import fastapi, httpx, pydantic, uvicorn; from skills.app import create_app"

health_json=$(curl --silent --show-error --fail "$BASE_URL/health")
ready_json=$(curl --silent --show-error --fail "$BASE_URL/ready")

HEALTH_JSON="$health_json" READY_JSON="$ready_json" "$APP_DIR/.venv/bin/python" - <<'PY'
import json
import os

health = json.loads(os.environ["HEALTH_JSON"])
ready = json.loads(os.environ["READY_JSON"])

assert health["service"] == "nyra-skills"
assert health["status"] == "ok"
assert ready["service"] == "nyra-skills"
assert ready["status"] == "ready"
PY

probe="$DATA_DIR/.write-test-$$"
: >"$probe"
rm -f "$probe"

if [[ -f $DATA_DIR/jobs.sqlite3 ]]; then
  sqlite3 "$DATA_DIR/jobs.sqlite3" "PRAGMA integrity_check" | grep -qx ok
fi

echo "Skills deployment verification passed"
