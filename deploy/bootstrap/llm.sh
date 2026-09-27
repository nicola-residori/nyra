#!/usr/bin/env bash
set -euo pipefail
SOURCE_ROOT=${SOURCE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
APP_DIR=${APP_DIR:-/opt/nyra-llm}
CONFIG_DIR=${CONFIG_DIR:-/etc/nyra}
CONFIG_FILE=${CONFIG_FILE:-$CONFIG_DIR/llm.env}
SERVICE_NAME=${SERVICE_NAME:-nyra-llm.service}
[[ ${EUID} -eq 0 ]] || { echo "llm bootstrap must run as root" >&2; exit 1; }
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl python3 python3-pip python3-venv
install -d -m 0755 "$APP_DIR"
install -d -m 0750 "$CONFIG_DIR"
rm -rf "$APP_DIR/llm" "$APP_DIR/shared"
cp -a "$SOURCE_ROOT/llm" "$APP_DIR/llm"
cp -a "$SOURCE_ROOT/shared" "$APP_DIR/shared"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip wheel
"$APP_DIR/.venv/bin/pip" install "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.8" "httpx>=0.27" "litellm"
if [[ ! -f $CONFIG_FILE ]]; then
  install -m 0600 /dev/null "$CONFIG_FILE"
  printf '%s\n' '# Provider secrets/config are operator-managed; no defaults are committed.' >"$CONFIG_FILE"
fi
install -m 0644 "$SOURCE_ROOT/deploy/systemd/nyra-llm.service" /etc/systemd/system/nyra-llm.service
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
for _ in $(seq 1 45); do
  curl -fsS http://127.0.0.1:8090/ready >/dev/null && break
  sleep 2
done
APP_DIR="$APP_DIR" CONFIG_FILE="$CONFIG_FILE" SERVICE_NAME="$SERVICE_NAME" "$SOURCE_ROOT/deploy/verify/llm.sh"
