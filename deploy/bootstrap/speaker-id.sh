#!/usr/bin/env bash
set -euo pipefail

SOURCE_ROOT=${SOURCE_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}
APP_DIR=${APP_DIR:-/opt/nyra-speaker-id}
DATA_DIR=${DATA_DIR:-/var/lib/nyra-speaker-id}
SERVICE_USER=${SERVICE_USER:-nyra-speaker-id}
PYTORCH_INDEX_URL=${PYTORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}

if [[ ${EUID} -ne 0 ]]; then
  echo "speaker-id bootstrap must run as root" >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl ffmpeg libsndfile1 python3 python3-pip python3-venv sqlite3

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$DATA_DIR" --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

install -d -o root -g root -m 0755 "$APP_DIR"
find "$APP_DIR" -mindepth 1 -maxdepth 1 ! -name .env -exec rm -rf {} +
cp -a "$SOURCE_ROOT/speaker-id/." "$APP_DIR/"
cp -a "$SOURCE_ROOT/shared" "$APP_DIR/shared"
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 \
  "$DATA_DIR" "$DATA_DIR/audio" "$DATA_DIR/models" "$DATA_DIR/models/huggingface"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip wheel
"$APP_DIR/.venv/bin/pip" install --index-url "$PYTORCH_INDEX_URL" torch torchaudio
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"
runuser -u "$SERVICE_USER" -- env \
  HOME="$DATA_DIR" \
  HF_HOME="$DATA_DIR/models/huggingface" \
  PYTHONPATH="$APP_DIR" \
  bash -c 'cd "$1" && exec "$2" -c "$3"' _ \
  "$APP_DIR" "$APP_DIR/.venv/bin/python" \
  "from embeddings import SpeechBrainECAPAEngine; SpeechBrainECAPAEngine(savedir='$DATA_DIR/models/ecapa').validate()"

install -m 0644 "$SOURCE_ROOT/deploy/systemd/nyra-speaker-id.service" \
  /etc/systemd/system/nyra-speaker-id.service
systemctl daemon-reload
systemctl enable nyra-speaker-id.service
systemctl restart nyra-speaker-id.service

for _ in $(seq 1 60); do
  if curl --silent --show-error --fail http://127.0.0.1:8090/health >/dev/null; then
    break
  fi
  sleep 2
done
APP_DIR="$APP_DIR" DATA_DIR="$DATA_DIR" SERVICE_USER="$SERVICE_USER" \
  "$SOURCE_ROOT/deploy/verify/speaker-id.sh"
