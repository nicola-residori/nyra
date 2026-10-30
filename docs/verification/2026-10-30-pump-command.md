# Pump off execution — 2026-10-30

## Reproduction and root cause

Production traces of the user's direct and polite/conditional pump-off requests
showed Skills MISS, rejected semantic routing, then discovery and a plain state
answer. No execute call was sent. One answer contradicted the observed on state.
The target was uniquely identified as a switch before any live operation.

Generic pump/pompa vocabulary was missing from the existing SWITCH command parser.
References containing grammatical links such as “pompa della piscina” also needed
normalization. Reasoning instructions emphasized read tools but lacked an explicit
action proposal contract, so discovering a target did not lead to execution.

## Change and verification

- Generic pump nouns now use the existing typed resolver/executor; no installation
  entity ID is hardcoded. Link words are removed without deleting identifiers such
  as “one” or corrupting a multiword area suffix.
- The area shortcut applies only to true generic resource terms. A bare pump name
  cannot resolve an unrelated room switch. Policy and ambiguity checks remain.
- Action requests, including conditional wording, have an explicit PROPOSED plan
  contract, separate from read-only reports. Verified already-done requests use an
  empty validated plan, emit no action and close listening.
- Model-supplied resolved IDs are ignored for LLM-origin execution. Router resolves
  the requested target afresh even if the provider includes a pre-resolved ID.
- Observed RED/GREEN tests cover three IT/EN pump phrasings, grammatical references,
  multiword area preservation, unrelated-switch rejection, numbered names, action
  and no-op contracts, and fresh resolution of an untrusted target ID.
- Independent review found the single-token area shortcut and identifier stripping
  regressions. Both were reproduced RED and fixed GREEN; no minors were deferred.
- Full suite: **1015 passed**, one existing dependency warning, 20.69 seconds.
  Python compile and git diff --check passed before commit/push.

## Live results

The original direct phrase “Spegni, pompa piscina.” was sent through Router after
deployment. The previously on target changed to off; Nyra returned “Fatto.” with
continue_conversation=false. Repeated HA reads retained off for 15 seconds.

The exact polite/conditional form (including duplicated “la”) correctly recognized
that the target was already off. After the no-op refinement it returned a truthful
already-off acknowledgment with continue_conversation=false. The target again
remained off through the stability window.

A separate provider test with synthetic on-state data returned a PROPOSED SWITCH /
TURN_OFF plan. It did not execute an action. The real pump was never turned on for
testing. HA-reported off is confirmed. The user subsequently confirmed that the physical
motor stopped, completing physical acceptance of the pump-off operation.
A read-only solar-report regression probe was also run after the action-prompt change.

## Deployment and rollback

a6e898c contains parser/resolver/action-contract fixes. Router/LLM additionally run
8d15210 (fresh target resolution and verified no-op handling); Skills remains on
a6e898c. No HA or speaker firmware update was required. Existing automations and
credentials were preserved, and no pump-on command was issued.

Protected code backups are under /opt/backups/nyra-pump-20261030 for Router and
/var/backups/nyra-pump-20261030 for Skills/LLM. Skills SQLite backup integrity was ok.
Restore affected code and restart the corresponding service for rollback, preserving
live data and credentials. A first post-restart smoke attempt arrived before HTTP
readiness; the final smoke was gated on readiness and passed.

Main remains unmerged. Other physical items, including unreliable timer wake
recognition and the unattributed room-light event, are unchanged by this fix.
