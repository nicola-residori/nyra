# Speaker-ID deployment

`nyra-speaker-id` runs in a dedicated Debian 12 LXC container. The reference
layout is `/opt/nyra-speaker-id` for immutable application files and
`/var/lib/nyra-speaker-id` for the SQLite database, profiles, diagnostics, and
model caches. The systemd service runs as the unprivileged
`nyra-speaker-id` user.

From a fresh checkout copied to the container, run as root:

```bash
chmod +x deploy/bootstrap/speaker-id.sh
deploy/bootstrap/speaker-id.sh
```

The bootstrap installs the CPU builds of PyTorch and TorchAudio, installs
SpeechBrain, downloads the ECAPA-TDNN model into the persistent data tree,
executes a local readiness inference, enables the service, and verifies both
endpoints:

```text
GET http://127.0.0.1:8090/health
GET http://127.0.0.1:8090/ready
```

`/health` reports process liveness. `/ready` returns HTTP 200 only after the
SQLite storage and ECAPA model are available; a missing or unloadable model
returns HTTP 503. Model acquisition therefore needs Internet access during the
first bootstrap. Later starts use the persistent cache.

The Router stream target for this deployment is:

```text
NYRA_SPEAKER_ID_STREAM_URL=ws://192.168.0.14:8090/v1/audio/stream
```

After deployment, reboot the container and repeat the health/readiness checks.
Confirm that `/var/lib/nyra-speaker-id/speaker-id.sqlite3`, profiles, threshold,
margin, and model cache remain present.
