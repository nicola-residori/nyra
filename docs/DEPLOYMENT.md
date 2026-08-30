# Router and Nyra Admin Deployment

The initial Debian 12 deployment runs two independent systemd services in the same CT:

- Nyra Router: `0.0.0.0:8090`
- Nyra Admin: `0.0.0.0:80`

Copy the repository to `/opt/nyra-router`, create `/opt/nyra-router/.env` from `.env.example`, then run:

```bash
cd /opt/nyra-router
bash deploy/bootstrap/router.sh
systemctl status nyra-router --no-pager
systemctl status nyra-admin --no-pager
curl -fsS http://127.0.0.1:8090/health
curl -fsS http://127.0.0.1/health
```
