#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT=${SOURCE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
APP_DIR=${APP_DIR:-/opt/nyra-skills}
DATA_DIR=${DATA_DIR:-/var/lib/nyra-skills}
CONFIG_DIR=${CONFIG_DIR:-/etc/nyra}
CONFIG_FILE=${CONFIG_FILE:-$CONFIG_DIR/skills.env}
SERVICE_NAME=${SERVICE_NAME:-nyra-skills.service}

if [[ ${EUID} -ne 0 ]]; then
  echo "skills bootstrap must run as root" >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl python3 python3-pip python3-venv sqlite3

install -d -o root -g root -m 0755 "$APP_DIR"
install -d -o root -g root -m 0750 "$DATA_DIR"
install -d -o root -g root -m 0750 "$CONFIG_DIR"

# Application replacement is intentionally scoped to code only.
# Persistent state in DATA_DIR and operator-managed CONFIG_FILE survives reruns.
rm -rf "$APP_DIR/skills" "$APP_DIR/shared"
cp -a "$SOURCE_ROOT/skills" "$APP_DIR/skills"
cp -a "$SOURCE_ROOT/shared" "$APP_DIR/shared"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip wheel
"$APP_DIR/.venv/bin/pip" install \
  "fastapi>=0.115" \
  "uvicorn[standard]>=0.30" \
  "pydantic>=2.8" \
  "httpx>=0.27"

if [[ ! -f $CONFIG_FILE ]]; then
  install -m 0600 /dev/null "$CONFIG_FILE"
  cat >"$CONFIG_FILE" <<EOF
NYRA_SKILLS_JOB_DB_PATH=$DATA_DIR/jobs.sqlite3
# NYRA_ROUTER_URL=http://router-host:8090
EOF
fi

install -m 0644 "$SOURCE_ROOT/deploy/systemd/nyra-skills.service" \
  /etc/systemd/system/nyra-skills.service

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

for _ in $(seq 1 45); do
  if curl --silent --show-error --fail http://127.0.0.1:8090/ready >/dev/null; then
    break
  fi
  sleep 2
done

APP_DIR="$APP_DIR" DATA_DIR="$DATA_DIR" CONFIG_FILE="$CONFIG_FILE" \
  SERVICE_NAME="$SERVICE_NAME" "$SOURCE_ROOT/deploy/verify/skills.sh"
