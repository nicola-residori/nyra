# Nyra Current State

## Version

Nyra v1.0-dev

## Current milestone

Router foundation, centralized logging/tracing, and Nyra Admin.

## Approved deployment

- `nyra-router`: port `8090`
- `nyra-admin`: port `80`

Router and Admin are separate applications and separate systemd services.

They may initially run in the same Proxmox container, but this is only a
deployment choice.

Nyra Admin communicates with Router exclusively through Router APIs and does not
access Router storage directly.

## Current design status

The design for Router foundation, Logging/Tracing v1, and Nyra Admin v1 has been
written and is awaiting final review before implementation planning.

## Existing alpha services

The current Nyra alpha implementation remains operational while Nyra v1 is
developed.

No alpha component will be removed until its v1 replacement is validated.

## Next step

Review and approve:

`docs/specs/2026-08-30-router-logging-admin-v1-design.md`

After approval, create the implementation plan and then implement Milestone 1.
