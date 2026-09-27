# Nyra LLM deployment

Application code lives in `/opt/nyra-llm`; operator-managed provider configuration and secrets live in `/etc/nyra/llm.env`. No provider secret is committed.

Use `deploy/bootstrap/llm.sh` to install/update code and systemd. Before any production change run `deploy/backup/llm.sh`; restore is guarded with `deploy/restore/llm.sh --config-file /etc/nyra/llm.env` and requires `--force` to overwrite an existing target.

Run `deploy/verify/llm.sh` after deployment and restart. Health/readiness checks are structural and readiness must not perform provider inference or any paid call.

Production deployment is a separate explicitly authorized phase. Verify rollback archive and configuration before changing Router/Skills/Admin wiring.

## Production state

Production verification completed on 2026-09-27. `nyra-llm` runs in CT `103`
at `192.168.0.11:8090` with `nyra-llm.service`; Router/Admin run in CT `108` at
`192.168.0.16`. The production-validated M6 branch revision is
`431bd00a0857f6c6c37e641c59cb31727f3bf7da`.

Authorized verification covered health/readiness, real `SEMANTIC`, buffered
Skills-CHECK-MISS `REASONING`, Router-mediated read-only capabilities, the
LLM-proposal -> Skills validation/materialization -> Router-capability gate,
forbidden capability rejection, controlled technical fallback, distributed
correlation, and physical Home Assistant/speaker paths.

Normal LLM observability is centralized through Router and contains technical
metadata only. Provider credentials remain operator-managed in
`/etc/nyra/llm.env` and are not committed.

The verified Router rollback archive created before the final semantic-lifecycle
hardening deployment is
`/opt/backups/nyra-router-pre-313d46c-20260927T123328Z.tgz`.
