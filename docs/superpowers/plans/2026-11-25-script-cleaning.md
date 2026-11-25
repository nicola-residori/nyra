# Script naming and Italian cleaning commands

User authorizes autonomous diagnosis/fix/deployment. Keep the confirmed wake-word configuration unchanged.

1. Reproduce explicit-script naming, global script lookup with speaker-area context, the missing-target clarification loop and Italian cleaning phrases using strict HA-like resource matching. Tests must not execute household actions.
2. Normalize explicit script references; resolve global scripts independently of current speaker room; route standard/aspiration/deep cleaning to existing typed SCRIPT/TRIGGER resources. Do not guess absent modes. Let unstructured clarification answers reach the existing LLM; recognize whole-utterance cancellation.
3. Teach the existing semantic routing prompt the same canonical script/cleaning vocabulary. Keep Router/Skills validation and ambiguity handling.
4. Run focused and broader regression tests, independently review, deploy only changed Python files with backups/source-hash checks, restart affected services and verify readiness. Probe real inventory through check/resolve only; never run Buonanotte or a robot as a test.
5. Document tested commands and limits; commit/push the scoped change. No firmware/wake changes.
