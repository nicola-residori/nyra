# Pump action routing

User reports repeated pool-pump off requests did not execute. Production traces show
Skills MISS, semantic rejection, discovery, then a plain textual state response
with no execution. One response even contradicted the observed on state.

Fix via TDD: generic pump nouns use the existing SWITCH resolver (not an installation
entity mapping), reference grammar is normalized before exact scoped resolution,
and reasoning has an explicit action-plan proposal contract separate from read-only
report instructions. Ambiguity, policy and Skills validation remain mandatory. A
conditional action must use observed state; reporting it is not action completion.

Run targeted/full tests and independent review; commit/push only green. Back up and
deploy Skills/LLM only, then test the user's requested OFF through Router and verify
HA state afterward. Never turn the pump on for testing. Main remains unmerged.

Execution ruling: Router needed a small area-resolution fix to prevent a pump noun
from taking an unrelated one-token generic switch shortcut. Grammar cleanup keeps
identifying words and area suffixes intact. Live provider output supplied a resolved
ID despite instructions, so Router now resolves every LLM-origin target afresh.
Verified no-ops use an empty validated plan, distinguishing completed commands from
continuing information responses. Evidence: docs/verification/2026-10-30-pump-command.md.
