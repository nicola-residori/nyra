# Speaker-ID deployment

`nyra-speaker-id` runs in a dedicated Debian 12 LXC container. The reference
layout is `/opt/nyra-speaker-id` for immutable application files and
`/var/lib/nyra-speaker-id` for the SQLite databases, profiles, diagnostics, and
model caches. The systemd service runs as the unprivileged
`nyra-speaker-id` user.

From a fresh checkout copied to the container, run as root:

```bash
chmod +x deploy/bootstrap/speaker-id.sh
deploy/bootstrap/speaker-id.sh
```

The bootstrap installs the CPU builds of PyTorch and TorchAudio, installs
SpeechBrain, downloads the ECAPA-TDNN model into the persistent data tree,
executes a local readiness inference, enables the service, and runs the shared
deployment verifier. The verifier checks the service account and layout,
Python dependencies, SQLite data, systemd enablement and activity, a real model
inference, and both endpoints:

```text
GET http://127.0.0.1:8090/health
GET http://127.0.0.1:8090/ready
```

`/health` reports process liveness. `/ready` returns HTTP 200 only after the
SQLite storage and ECAPA model are available; a missing or unloadable model
returns HTTP 503. Model acquisition therefore needs Internet access during the
first bootstrap. Later starts use the persistent cache.

The same verification can be repeated without reinstalling:

```bash
deploy/verify/speaker-id.sh
```

The Router stream target for this deployment is:

```text
NYRA_SPEAKER_ID_STREAM_URL=ws://192.168.0.14:8090/v1/audio/stream
```

To verify persistence across a reboot, save a non-sensitive state manifest,
reboot the container, and compare the live state with it:

```bash
deploy/verify/speaker-id.sh --snapshot /root/nyra-speaker-id-before-reboot.json
systemctl reboot
# After reconnecting:
deploy/verify/speaker-id.sh --verify-snapshot /root/nyra-speaker-id-before-reboot.json
```

The manifest contains the schema, threshold/margin/revision, aggregate profile,
enrollment and wake-word counts, and whether the model cache is populated. It
contains no audio, embeddings, user identifiers, or credentials.
