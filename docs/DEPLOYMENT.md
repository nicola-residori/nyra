# Nyra Deployment

Nyra deployments must be reproducible from the repository. Manual installation steps used during development must eventually be represented by versioned scripts or documented procedures.

The repository is the source of truth; running containers are deployment targets.

The first supported target is Proxmox using Debian containers. Planned first-level components include nyra-router, nyra-skills, nyra-memory, nyra-voice, and nyra-llm.

Installation-specific values such as IP addresses, DNS names, API tokens, credentials, Proxmox storage names, container IDs, and bridges must not be hardcoded.

Planned deployment tooling:

```text
deploy/
├── proxmox/
├── bootstrap/
└── systemd/
```
