#!/usr/bin/env bash
set -euo pipefail
APP_DIR=${APP_DIR:-/opt/nyra-router}
apt-get update
apt-get install -y python3 python3-venv python3-pip curl sqlite3
cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e '.[test]'
mkdir -p data
install -m 0644 deploy/systemd/nyra-router.service /etc/systemd/system/nyra-router.service
install -m 0644 deploy/systemd/nyra-admin.service /etc/systemd/system/nyra-admin.service
systemctl daemon-reload
systemctl enable nyra-router.service nyra-admin.service
systemctl restart nyra-router.service nyra-admin.service
