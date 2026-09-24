# Review correction build — 2026-09-24

AK authorized implementation corrections and push to existing PR30 after the local
assessment of review 5308021468. No merge, activation or live-money action is in
scope. This reuses issue27 build iteration2 and its existing plan/acceptance scope;
historical reports and source identities remain historical.

All three review findings are accepted and implemented:
- Native reconciliation examines every trailing attempt. Non-fill termination of
  an established order exits only when no active verified native trail covers the
  whole residual position. Actual protective fills still latch full-residual exit.
  Single-trail termination and unknown/rejected submission intervention remain.
- Preflight keeps QUEUED only on typed transient info-read errors, with authority
  and expiry checked before and after reads. HTTP permanent failures, identity and
  schema failures reject. There is no signed send retry or new execution lifecycle.
- Capital reconciliation rejects nonzero/malformed escrow and borrowed/supplied
  components and contradictory portfolio-margin evidence. Valid zero components
  add no capital. No inferred valuation or mode expansion is introduced.

Regression tests were introduced first. The original candidate produced 24
assertion failures and two missing-type errors in 20 tests; assertion failures
reproduce the actual coverage/capital defects, while the missing transient type is
an implementation prerequisite, not independent behavioral proof. The focused
post-fix conditional-add/native-trailing suite passed 66 tests. Transport tests
also distinguish transient HTTP/network failures from permanent HTTP errors.

Changed owner docs cover capital, bounded reads, native termination, and residual
exits; the shared Hyperliquid error reference describes the typed read exception.
Both CLI skill links retain the same canonical source. Existing flow artifacts
remain applicable: corrections are local guards/reconciliation inside the same
supervisor, without structural flow, lifecycle, schema or provider changes.

Source identity and diff: `review-fix-candidate.json`, `review-fix-changes.diff`.
Independent findings/validation: `review-fix-independent.md` and
`review-fix-verification.md`. The original reproduction script/results target the
old PR head and intentionally are not a test of corrected behavior.

Review disposition is implementation plus local verification, not reviewer
resolution or merge approval. The remote reviewer may re-review the pushed head.
