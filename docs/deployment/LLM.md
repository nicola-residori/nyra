# Nyra LLM deployment

Application code lives in `/opt/nyra-llm`; operator-managed provider configuration and secrets live in `/etc/nyra/llm.env`. No provider secret is committed.

Use `deploy/bootstrap/llm.sh` to install/update code and systemd. Before any production change run `deploy/backup/llm.sh`; restore is guarded with `deploy/restore/llm.sh --config-file /etc/nyra/llm.env` and requires `--force` to overwrite an existing target.

Run `deploy/verify/llm.sh` after deployment and restart. Health/readiness checks are structural and readiness must not perform provider inference or any paid call.

Production deployment is a separate explicitly authorized phase. Verify rollback archive and configuration before changing Router/Skills/Admin wiring.
