# Post-merge lifecycle build

Both defects from issue27 comment5827258589 are corrected.
- Cancellation start now lives on each entry/add attempt, persisted before cancel
  effects and unknown-target intervention. Existing per-target retry/deadline checks
  are unchanged. Legacy target cancel history supplies its original start; a legacy
  owner clock is usable only inside that target's creation/known-cancel interval.
- Terminal saves retire only QUEUED/no-durable-attempt tranches in a serialized
  SQLite transaction. Finished-owner ticks repair older rows or a crash between
  terminal save and retirement. CANCELED/reason/retired_ms preserve evidence; any
  durable attempt and every non-QUEUED status remain untouched. No schema change.
- New lifecycle regressions and additional CLI/SQLite smoke cover historical entry
  cancellation, new add expiry, partial fill during cancel, full exit and legacy
  queued-tranche repair. Status queries remain read-only.
- Owner operations docs updated. Existing overview updated and focused cancellation/
  retirement diagram added. Both pass showcase9/9, browser and perceptual checks;
  final source alignment is recorded separately. Current browser sidecars move from
  docs to the scoped diagram report directory, replacing obsolete tracked sidecars.

Intended Red:8tests,4failures+2expected missing-clock errors. Initial35test run also
collected imported fixture tests; import changed to module reference so new tests
are counted once. Green69tests and additional11boundary tests pass. Final scope221
tests passes; separate expanded smoke passes after that run. Evidence and exact
commands: verification.md and test-results.json. All venue behavior is stubbed.

Use candidate.json for source identity, including deleted obsolete browser sidecars;
changes.diff is normalized retained evidence. The independent verifier must inspect
actual code and every boundary, not infer PASS from these author results.
User-selected Grok4.7/high/auto supersedes the default medium setting; see reviewer
request and runtime receipts. No live account/protection or activation changed.
