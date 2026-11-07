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
- Complete suite: **991 passed, one existing dependency warning**, 16.50s. Python
  compilation, Bash runner syntax and `git diff --check` pass.

## Deployment and physical validation

Protected code/config backups exist on Router, LLM and HA. Router's SQLite backup was
created with SQLite backup API and integrity check returned `ok`. Installation-specific
credentials remain outside the repository. Router/LLM and both speaker firmware sources are `7ee136a1dcb03c55a819089f7525a3f7881ae75b`;
HA additionally runs the audio-correlation fix `cccc0b0e260e984e89eee17a142165867aef6417`.
The latter applies the audio generation before Speaker-ID correlation IDs are
allocated, preventing an interrupted conversation from tagging audio with old IDs.
Its targeted regression was RED (missing generation boundary), then GREEN; the
complete suite is the 991-test result above.

Both full ESPHome 2026.10.1 builds passed. Final configuration hashes are
`0x0028e129` and `0xd2fa9833`, with build times 14:00:49 and 14:01:01 Europe/Rome.
Both encrypted OTA uploads succeeded and both devices passed 65 seconds of repeated
encrypted API round trips, retaining the new compilation timestamps and alert
entities. Shared HA ESPHome sources match the committed firmware source; original
entrypoints and credentials are preserved.

HA configuration checks and restart succeeded. Authenticated API reports HA
2026.10.4 RUNNING after the final update. Live safe tests verified:

- clarification now returns a valid question with continuation, instead of provider
  validation failure;
- a completed book-conversation response without a question continues, and the next
  turn understands which book was discussed;
- “Ok grazie!” closes with no continuation;
- “Elenca i timer” completes with no continuation and no audio/job side effect;
- HA's actual conversation agent returns continuation true for general dialogue and
  false after closing, verified again after the final HA restart.

An initial synthetic probe during the planned HA restart returned
`SKILLS_UNAVAILABLE`; gating the rerun on HA RUNNING produced the passing results.
No user timers were cancelled; no active SCHEDULED/RUNNING jobs existed before OTA.
Main remains unchanged and the PR remains draft. Acoustic recognition remains pending: the prior test
needed multiple wake words, and the VAD filter rejected another detection. No VAD or
model threshold is changed by this patch.

## Physical feedback — 2026-10-30

The user confirmed that a general conversation about a film reopened listening and
that “ok grazie” closed it. The user subsequently confirmed that ordinary commands execute and close listening
without reopening. All three physical dialog checks pass.

The user could not reliably interrupt a timer with the wake word. That physical
check remains unaccepted. The latest timer ledger is STOPPED after approximately
51 seconds against a 60-second limit; this does not establish prompt wake detection
or identify the stop cause. The bounded live diagnostic window had already ended,
so it provides no detector trace for this particular test. No further thresholds or
models were changed based on this feedback. Model training versus playback masking
or VAD gating has not been isolated. Room-light activation remains unattributed.
