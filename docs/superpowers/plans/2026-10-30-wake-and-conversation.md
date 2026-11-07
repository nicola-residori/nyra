# Wake handoff and conversational listening

> Execute inline with TDD; user explicitly approved proceeding and supplied the final behavior.

Goal: one wake stops current Nyra audio and opens listening; commands finish unless ambiguous; conversational turns reopen listening until an exact closing phrase or silence/error/alert interruption.

Architecture: preserve ESPHome's native continuation after TTS. Router declares continuation explicitly, independently of request completion. A completed conversational turn uses a fresh request in the same session; clarification resumes the current request. Persist assistant responses alongside user turns for bounded history. Exact normalized closing phrases are handled deterministically before Skills/LLM routing. Do not relax side-effect validation or infer continuation from punctuation.

1. RED/GREEN wake automation: explore its busy/idle control-flow paths; replace stop-only branching with stop/settle followed by a shared restartable listening sequence. Preserve mute and epoch guards. Compile both speakers.
2. RED/GREEN conversational lifecycle: explicit response flag; plain LLM replies continue, executed action plans and Skills commands do not; clarification continues; explicit close terminates; HA preserves session/new request correctly; history includes assistant replies and remains bounded. Reproduce the live provider's clarification plus duplicate response_text; normalize only redundant text at the provider boundary, keeping invalid actions rejected.
3. Run targeted and complete suite, diff check, independent review and compile. Commit/push only green. Back up affected production code/database/config; deploy and verify safe synthetic conversational/command/closing turns and encrypted speaker stability. Acoustic sensitivity remains a separate unresolved physical check; do not change VAD thresholds without measurements. Main stays unmerged.

Rulings: a conversational answer remains open even if it contains no question, as requested. Native silence timeout ends capture; no always-running/continuous microphone mode is introduced. Exact close phrases include IT grazie/chiudi/ok grazie/ok and EN thanks/thank you/close/okay thanks/okay; phrases embedded in longer requests must not close them.
