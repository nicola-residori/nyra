# Italian scripts and cleaning commands

Updated 2026-11-25. This change concerns request interpretation only; the confirmed server wake-word setup remains unchanged.

## Named Home Assistant scripts

- `esegui lo script della buonanotte` → `script.buonanotte`.
- `attiva la buonanotte` or `buonanotte` uses named-resource resolution. Multiple matching scripts/scenes/automations still require clarification.
- During a missing-target clarification, `È uno script, si chiama buonanotte` corrects a previous wrong resource kind. The same declarative sentence without an actionable pending request is not a deterministic trigger.
- `annulla`, `annulla tutto`, `lascia stare`, `cancel` close the current conversation/request. They do **not** cancel a running household script, robot, timer or job. Specific commands such as `annulla il timer` are not treated as session closure.

Global scripts/scenes/automations are not filtered by the current speaker's room. Allowed-resource policy remains enforced. Room-scoped physical device lookup is preserved.

## Cleaning vocabulary

| Spoken command | Script reference / mode |
| --- | --- |
| `pulisci zona giorno` | `pulizia zona giorno standard` |
| `aspira zona giorno` | `pulizia zona giorno aspirazione` |
| `pulisci profondamente zona giorno` | `pulizia zona giorno profonda` |
| `pulisci a fondo la zona giorno` | `pulizia zona giorno profonda` |

Other zones use the same vocabulary, resolved against actual existing Home Assistant scripts rather than invented entity IDs. The inspected inventory includes zone giorno/notte, piano terra, kitchen/living room, bedrooms, bathrooms, corridor, gym and Mansarda. Not every mode exists for every zone: an absent aspiration script must not run standard or deep cleaning instead.

Alternative wording/modifiers (for example `pulisci zona giorno a fondo` or `passa solo l'aspirapolvere in cucina`) is left to the existing LLM semantic routing path. Its typed SCRIPT/TRIGGER proposal still passes through Skills and Router resource resolution/policy before execution. Ambiguous or missing targets require clarification; an LLM proposal is not authorization to invent a target or mode.

## Diagnosis and validation

The user-reported request history showed repeated missing-target clarification, including after an explicit script correction and cancellation. The named script exists. Regression tests reproduce missing room association for a global script, resource-label/article parsing failures, and the clarification loop that retained the wrong resource kind. Full-turn input text was inspected privately; personal conversation transcripts and IDs are not committed here.

Testing uses strict simulated HA inventory and records intended service calls without executing household actions. Focused/broader regression suite: 236 passing tests on the final changed sources. Checks include global script resolution, exact cleaning mode selection, missing-mode non-substitution, no deterministic execution for discussion/negation/scheduling, existing light follow-up semantics and unrelated Skills behavior. Live verification uses interpretation and read-only resolution only. Physical script/robot execution is not exercised as a diagnostic test.

Deployed Router/Skills/LLM source files were checked against their pre-change hashes and backed up before atomic replacement. All three services reported ready afterwards. Seven live check/resolve probes passed, including two using the actual LLM and the existing semantic safety bridge; no execution endpoint was called. See [live receipt](deployment/ITALIAN_COMMANDS_2026-11-25.json) and `tools/check_italian_home_commands.py`. A complete physical voice-to-script/robot action remains for normal user use.
