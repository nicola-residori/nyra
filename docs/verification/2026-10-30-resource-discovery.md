# Report discovery and clarification — 2026-10-30

## Outcome

Deployed read-only report discovery finds photovoltaic measurements and separately
identified forecasts across Italian/English resource names. The original requests
“Mi dici lo stato del fotovoltaico?” and “Fammi un resoconto del fotovoltaico” now
complete with available power/energy and forecast data. An unidentifiable system
requests a name/identifier and continues listening. These are authenticated live
service tests. The user subsequently confirmed the physical voice test: Nyra now
provides a useful photovoltaic report. Voice acceptance for this request passes.

## Root causes and changes

The original physical request did reach LLM discovery. Its next NEEDS_CAPABILITY
response included a spoken preamble in response_text and failed outcome validation.
Only redundant preambles are normalized; typed action/outcome validators remain.
Technical LLM unavailability no longer falls through to the stock HA agent's
unrelated unknown-device response.

Discovery previously used literal substring matching and omitted units. It now
supports generic topic aliases and numbered PV inputs, alternative keyword hints,
policy filtering before ranking, bounded 20-resource output, measurement units,
device/state classes, native timestamps and counter last_reset evidence. Explicit
user solar/battery topics constrain broader model-added hints, preventing unrelated
energy devices from filling the result window. This affects read discovery only;
actuator resolution and authorization are not broadened.

The reasoning loop retains earlier tool results and exposes its remaining tool
budget to the provider. Existing hard round/time limits remain enforced. The
provider is instructed to use discovered facts, distinguish forecasts and settings,
avoid inventing periods/history, and ask for missing scope.

A missing actuator target returns clarification rather than terminal failure. Its
follow-up retains the original operation, resource type, cardinality and area; a
bare room/name answer cannot trigger an unrelated same-named scene.

## Verification

- Observed RED/GREEN regressions cover provider capability preambles, missing-target
  questions (IT/EN), preserved search results, tool contracts, translated metadata,
  numbered PV channels, multi-keyword queries, budget visibility, topic crowding,
  counter-reset metadata and truthful technical-error handling.
- Independent review found an unrelated-scene collision and lost numbered PV
  matches. Both were reproduced RED and fixed GREEN; no minors were deferred.
- The existing integration test requiring NOT_FOUND to terminate was updated to the
  user-requested clarification contract. Other routing failures remain failures.
- Final full suite: **1005 passed**, one existing dependency warning, 20.40 seconds.
  Python compile checks and git diff --check pass.
- Initial controlled live probes revealed overly conjunctive keyword matching and
  later generic energy result crowding. Regressions reproduce both; final live
  requests find instantaneous power, generated energy and separately labelled
  forecasts. Counter reset evidence was independently verified and is now exposed.
- A final unknown-system probe returns NEEDS_CLARIFICATION with a request for a
  name/identifier and continue_conversation=true. A report explicitly asking for
  actual readings versus forecasts also completes with that distinction.

## Deployment, boundaries and rollback

Changes were pushed to feat/persistent-voice-alerts, never merged to main.
Initial release f85e390 runs in Skills/HA. Router/LLM include 684e7c7; Router also
includes e6ea95b counter-reset metadata. Earlier query-budget correction is a5741f1.
Services were restarted, HA configuration checks/restart passed, and authenticated
HA readiness reported RUNNING. No firmware or credentials changed in this extension.

Protected pre-change code backups exist under /opt/backups/nyra-discovery-20261030
(Router), /var/backups/nyra-discovery-20261030 (LLM/Skills), and
/config/nyra-backups/20261030/ha-before-discovery.tgz (HA). Consistent SQLite backups
for Router and Skills passed integrity_check=ok. Restore affected code from these
archives and restart the corresponding services; preserve current live databases,
credentials and jobs. No database schema change is introduced by this extension.

This contract reads current states/attributes; arbitrary historical series and
period aggregation are not added. Counter periods require reset evidence. Native
ISO timestamps retain their offsets; report timezone localization remains a
separate validation item. Synonym coverage is a small generic topic vocabulary,
not an installation inventory or a guarantee for every possible naming convention.
The prior unreliable timer wake detection and unattributed room-light activation
remain unresolved independent physical items.
