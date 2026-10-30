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
