#!/bin/bash
# Bash 3.2 compatible. Read-only local/live verification; never starts audio.
set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_DIR"
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -m pytest -q
"$PYTHON_BIN" -m compileall -q skills router shared homeassistant/custom_components/nyra
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git diff --check
fi
if [ -n "${ESPHOME_CONFIG:-}" ]; then
  "$PYTHON_BIN" -m esphome compile "$ESPHOME_CONFIG"
fi
# Optional service checks require operator-supplied endpoints. No credentials printed.
"$PYTHON_BIN" - <<'PY'
import os
import httpx
from shared.protocol.alerts import AlertResponse, AlertState
for variable in ('NYRA_ROUTER_URL', 'NYRA_SKILLS_URL'):
    url=os.environ.get(variable)
    if not url:
        continue
    for path in ('/health','/ready'):
        response=httpx.get(url.rstrip('/')+path,timeout=10)
        response.raise_for_status()
    print(variable+': health/ready OK')
url=os.environ.get('NYRA_HA_URL')
source=os.environ.get('NYRA_VERIFY_SOURCE_ID')
if url and source:
    token=os.environ['NYRA_HA_TOKEN']
    response=httpx.post(url.rstrip('/')+'/api/nyra/alerts',
        headers={'Authorization':'Bearer '+token},
        json={'action':'STATUS','job_id':'job_verification_probe','source_id':source},timeout=10)
    response.raise_for_status()
    result=AlertResponse.model_validate(response.json())
    assert result.state is AlertState.NOT_FOUND, result.state
    print('HA authenticated audio contract OK; no playback requested')
PY
printf '%s\n' 'Software verification complete. Physical checks remain in docs/voice-alerts.md.'
