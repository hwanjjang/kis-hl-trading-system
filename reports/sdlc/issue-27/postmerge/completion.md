# Post-merge correction candidate handoff

Both reported defects are fixed and independently verified. AC2/AC3 now bind
cancellation timing to the actual target attempt, including restart and legacy
history. AC2/AC5 retire terminal-owner unsent queued adds, preserve signed history
and repair older snapshots. AC1/AC4 arithmetic and full-position exits are unchanged
and included in the221-test regression scope. Source identity: candidate.json.

Main verification:11focused tests,221changed-scope tests and expanded actual
CLI/tempSQLite smoke PASS. Grok4.7/high/auto independent verification PASS:
221tests,11focused tests,10independent probes and smoke; no findings. See
grok-independent.md, reviewer-runtime.json and identity-notes.md for evidence
and explicit high-effort override of the generic medium setting.

Updated conditional-add diagram and new add-termination diagram both pass
Archify showcase9/9, Chromium/browser and image checks, final source alignment.
Source/HTML/evidence are retained in docs/architecture and this report directory.

This completes the historical local-route candidate stage. User continuation
authorizes a follow-up PR and separate exact-head Grok review; those publication
records follow on the PR and do not require recursive evidence-only commits.
At this precommit handoff, publication/CI/exact-head review are pending. This is
not a claim of default-medium gate compliance or merge readiness. All trading
checks are offline; no live account/protection changes or activation occurred.
No new merge/auto-merge/queue authorization. #28 discretionary half exits remain
deferred. AK owns subsequent merge/deployment/activation decisions.
