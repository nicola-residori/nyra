#!/usr/bin/env bash
set -euo pipefail
APP_DIR=${APP_DIR:-/opt/nyra-llm}
CONFIG_FILE=${CONFIG_FILE:-/etc/nyra/llm.env}
SERVICE_NAME=${SERVICE_NAME:-nyra-llm.service}
BASE_URL=${BASE_URL:-http://127.0.0.1:8090}
[[ ${EUID} -eq 0 ]] || exit 1
test -f "$APP_DIR/llm/app.py"
test -d "$APP_DIR/shared"
test -x "$APP_DIR/.venv/bin/python"
test -f "$CONFIG_FILE"
systemctl is-enabled --quiet "$SERVICE_NAME"
systemctl is-active --quiet "$SERVICE_NAME"
PYTHONPATH="$APP_DIR" "$APP_DIR/.venv/bin/python" -c "from llm.app import create_app"
curl -fsS "$BASE_URL/health" >/dev/null
# /ready is structural only and MUST NOT trigger provider inference or billable calls.
curl -fsS "$BASE_URL/ready" >/dev/null
echo "LLM deployment verification passed"
