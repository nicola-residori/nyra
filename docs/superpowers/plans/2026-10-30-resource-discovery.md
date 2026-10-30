# Resource discovery and useful clarification

User request: a report/query must search available HA data, then ask for missing
scope rather than fall through to “not understood/device not found”.

Evidence: the physical photovoltaic query reached DISCOVER_RESOURCES, then the
provider emitted NEEDS_CAPABILITY plus response_text, failing strict validation.
Installed entities include actual solar power/energy and separately named forecasts,
with mixed Italian/English names. Current discovery uses a literal substring and
omits units; the orchestrator discards all but its last capability result.

Inline TDD tasks:
1. Reproduce and normalize redundant provider preambles for NEEDS_CAPABILITY only,
   keeping strict action/outcome validators intact.
2. Exercise policy-scoped multilingual topic discovery with measurement metadata;
   add generic token/topic aliases, bounded ranked results, without installation IDs.
   Preserve all capability results within the existing reasoning round budget.
3. Give the provider an explicit read-tool contract and instructions to discover
   before claiming missing data, distinguish measured/forecast and units, avoid
   invented historical periods, and use typed clarification for genuine ambiguity.
   Missing actuator targets ask for a name/area with trusted pending context;
   clarification must never itself execute anything.
4. Targeted/full tests, diff check, independent review, protected backups, commit/push
   only green, deploy Router/LLM/Skills only. Live read-only solar and missing-topic
   probes. No firmware change, no main merge. Historical aggregation is not invented
   from a current-state-only contract.
