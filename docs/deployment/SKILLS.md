# Nyra Skills deployment

This guide defines the repository-owned deployment, verification, backup, and
restore assets for the dedicated `nyra-skills` service.

## Layout

The default layout is intentionally split between replaceable application code
and persistent state:

- application: `/opt/nyra-skills`
- persistent job database: `/var/lib/nyra-skills/jobs.sqlite3`
- operator-managed environment: `/etc/nyra/skills.env`
- systemd service: `nyra-skills.service`
- default listen address: `0.0.0.0:8090`

The bootstrap script replaces application code but does not delete the
persistent data directory or an existing environment file.

## Bootstrap

Run from a checked-out, verified repository revision on the target host:

```bash
sudo deploy/bootstrap/skills.sh
```

The script installs runtime dependencies, copies `skills/` and `shared/`,
creates the virtual environment, installs the systemd unit, enables/restarts the
service, waits for readiness, and runs the verifier.

`NYRA_ROUTER_URL` belongs in `/etc/nyra/skills.env`. Credentials for Home
Assistant are not part of Skills configuration.

## Verification

```bash
sudo deploy/verify/skills.sh
```

The verifier checks:

- expected application files and Python environment;
- persistent directory exists and is writable;
- systemd service is enabled and active;
- service runs as `root` with the expected working directory;
- `/health` returns `nyra-skills` / `ok`;
- `/ready` returns `nyra-skills` / `ready`;
- the existing job database passes SQLite integrity checking.

## Backup

```bash
sudo deploy/backup/skills.sh
```

Or choose an explicit output path:

```bash
sudo deploy/backup/skills.sh /safe/path/nyra-skills-before-deploy.tar.gz
```

The archive contains the persistent jobs database when present, the Skills
environment file, and checksums. The live SQLite database is copied using the
SQLite backup command so WAL state is handled safely.

## Restore

Restore is intentionally conservative. The service must be stopped and target
paths must be stated explicitly:

```bash
sudo systemctl stop nyra-skills.service

sudo deploy/restore/skills.sh /safe/path/nyra-skills-before-deploy.tar.gz \
  --data-dir /var/lib/nyra-skills \
  --config-file /etc/nyra/skills.env
```

If either destination already exists, restore refuses to overwrite it. After
inspection, `--force` is required for replacement:

```bash
sudo deploy/restore/skills.sh /safe/path/nyra-skills-before-deploy.tar.gz \
  --data-dir /var/lib/nyra-skills \
  --config-file /etc/nyra/skills.env \
  --force
```

Then:

```bash
sudo systemctl start nyra-skills.service
sudo deploy/verify/skills.sh
```

## Production gate

These assets do not authorize a deployment. M5 Task 19 requires explicit
production authorization after integration regression is green, actual target
state has been inspected, and a backup/rollback artifact has been created and
verified.
