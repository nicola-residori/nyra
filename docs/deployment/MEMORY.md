# Nyra Memory deployment

Nyra Memory runs in a dedicated Debian 12 container. Only Router communicates
with it during request processing or administration. Nyra Admin and Home
Assistant use Router APIs and never receive the private Memory address.

## Runtime layout

- application: `/opt/nyra-memory`
- service account: `nyra-memory` with no login shell
- database: `/var/lib/nyra-memory/memory.sqlite3`
- model cache: `/var/lib/nyra-memory/models/huggingface`
- private HTTP port: `8090`
- systemd unit: `nyra-memory.service`

The SQLite database uses WAL during normal operation. The embedding model is
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` unless
`NYRA_MEMORY_MODEL` overrides it. Readiness requires an initialized writable
database and a loaded embedding provider.

## Bootstrap

Copy a clean repository checkout into the container, then run as root:

```bash
SOURCE_ROOT=/root/nyra deploy/bootstrap/memory.sh
```

The bootstrap creates the locked user, installs the Python environment,
downloads the model into persistent storage, enables the service, and finishes
with the shared verifier.

On the Router host set the private address and bounded timeout in
`/opt/nyra-router/.env`:

```dotenv
NYRA_MEMORY_URL=http://MEMORY_PRIVATE_IP:8090
NYRA_MEMORY_TIMEOUT_SECONDS=3.0
```

Deploy the matching Router and Admin revision, restart both services, then
check Router `/ready`. Router reports `MEMORY_NOT_READY` when the dependency is
unavailable while its health and unrelated administration remain reachable.

## Verification and reboot

Run the verifier as root:

```bash
deploy/verify/memory.sh
```

For a persistence check around a reboot:

```bash
deploy/verify/memory.sh --snapshot /root/memory-before-reboot.json
reboot
deploy/verify/memory.sh --verify-snapshot /root/memory-before-reboot.json
```

The check covers the service user, systemd state, SQLite integrity, schema,
record counts, model cache, `/health`, `/ready`, and the configured embedding
model.

## Backup

Create a transactionally consistent SQLite backup and SHA-256 manifest:

```bash
deploy/backup/memory.sh /var/backups/nyra-memory/manual.tar.gz
```

The model cache is reproducible and is not included. Keep the backup outside
the container or include it in the host backup policy.

## Restore

Restore refuses to run while `nyra-memory` is active:

```bash
systemctl stop nyra-memory
deploy/restore/memory.sh /var/backups/nyra-memory/manual.tar.gz
systemctl start nyra-memory
deploy/verify/memory.sh
```

The restore accepts only the database and checksum manifest, verifies the
hash and SQLite integrity, and installs the database with the service owner.

## rollback

Before deploying a new revision, create a Memory backup and preserve the
current Router and Admin application directories or package. To roll back:

1. stop Router writes and `nyra-memory`;
2. restore the previous Memory backup;
3. restore the previous Router and Admin revision and their environment files;
4. start Memory, Router, and Admin in that order;
5. run the Memory verifier and check Router `/health` and `/ready`;
6. perform an operational lookup and a read-only semantic search.

Do not derive deletion or supersession targets from similarity results. Admin
mutations must carry the exact selected record ID and an idempotency key.
