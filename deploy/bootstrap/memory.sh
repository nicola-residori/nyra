#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT=${SOURCE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
APP_DIR=${APP_DIR:-/opt/nyra-memory}
DATA_DIR=${DATA_DIR:-/var/lib/nyra-memory}
SERVICE_USER=${SERVICE_USER:-nyra-memory}

if [[ ${EUID} -ne 0 ]]; then
  echo "memory bootstrap must run as root" >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl python3 python3-pip python3-venv sqlite3

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$DATA_DIR" --create-home \
    --shell /usr/sbin/nologin "$SERVICE_USER"
fi

install -d -o root -g root -m 0755 "$APP_DIR" "$APP_DIR/memory"
find "$APP_DIR/memory" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
cp -a "$SOURCE_ROOT/memory/." "$APP_DIR/memory/"
rm -rf "$APP_DIR/shared"
cp -a "$SOURCE_ROOT/shared" "$APP_DIR/shared"

install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 \
  "$DATA_DIR" "$DATA_DIR/models" "$DATA_DIR/models/huggingface"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip wheel
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/memory/requirements.txt"

chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"
runuser -u "$SERVICE_USER" -- env \
  HOME="$DATA_DIR" \
  HF_HOME="$DATA_DIR/models/huggingface" \
  PYTHONPATH="$APP_DIR" \
  NYRA_MEMORY_DATA_ROOT="$DATA_DIR" \
  "$APP_DIR/.venv/bin/python" -c \
  "from memory.embeddings import SentenceTransformerEmbeddingProvider; SentenceTransformerEmbeddingProvider('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2').prepare()"

install -m 0644 "$SOURCE_ROOT/deploy/systemd/nyra-memory.service" \
  /etc/systemd/system/nyra-memory.service
systemctl daemon-reload
systemctl enable nyra-memory.service
systemctl restart nyra-memory.service

for _ in $(seq 1 90); do
  if curl --silent --show-error --fail http://127.0.0.1:8090/ready >/dev/null; then
    break
  fi
  sleep 2
done

APP_DIR="$APP_DIR" DATA_DIR="$DATA_DIR" SERVICE_USER="$SERVICE_USER" \
  "$SOURCE_ROOT/deploy/verify/memory.sh"
