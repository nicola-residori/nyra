# Wake handoff and conversational listening — 2026-10-30

Requirements: one wake interrupts current audio and opens listening. Commands finish
unless ambiguous; conversation keeps reopening until closing phrase, silence/error,
or a higher-priority alert. Main merge remains unauthorized.

## Reproduction and regression evidence

- Live safe book-conversation probe returned `LLM_UNAVAILABLE`; service logs identified
  a `NEEDS_CLARIFICATION` result rejected for an extra `response_text` preamble. A
  direct provider probe reproduced a typed question plus preamble, with no action plan.
- Provider-boundary RED/GREEN regression canonicalizes only the redundant text. Strict
  action-plan/outcome validators remain unchanged and invalid action payloads reject.
- Wake automation busy path failed the reachability regression (stop without start).
  Shared restartable stop/settle/cue/listen handoff now covers busy and idle paths.
- Explicit continuation regression was demonstrated RED with the flag disabled and
  GREEN restored; closing phrases, commands, session/new request ownership, legacy
  SQLite migration and bounded two-sided history are covered.
- Clarification-history regression failed before preserving intermediate answers;
  review additionally found current-request history missing during the resume call.
  The second-call and third-call assertions both pass after the fix.
- Independent review found stale overlap cleanup and a two-second handoff abandonment.
  Three deterministic overlap cases (old response, error, cancellation) were RED,
  then GREEN with generation-specific IDs and ownership-scoped cleanup. A three-second
  old-pipeline cancellation simulation was RED at two seconds, then GREEN with pending
  handoff cancelled explicitly by mute/new alert. No minor findings were deferred.
- Complete suite: **990 passed, one existing dependency warning**, 19.07s. Python
  compilation, Bash runner syntax and `git diff --check` pass.

## Deployment and physical validation

Protected code/config backups exist on Router, LLM and HA. Router's SQLite backup was
created with SQLite backup API and integrity check returned `ok`. Installation-specific
credentials remain outside the repository. Firmware compilation and deployment evidence
will be added after completion. Acoustic recognition remains pending: the prior test
needed multiple wake words, and the VAD filter rejected another detection. No VAD or
model threshold is changed by this patch.
