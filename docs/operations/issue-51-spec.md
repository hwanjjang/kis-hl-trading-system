# Issue 51: specification
Owner root; 2026-10-03; revision 1; PROCEED. Input: issue-51-development.md revision 1.

Persist `side` on policy and position JSON; default absence to long. Short keeps
`low` and `bucket_low`, initialized at entry. Completed covered consecutive
nine-minute buckets lower the watermark and threshold `min(old, low + distance)`.
Fresh price >= threshold creates durable intent. Long behavior stays unchanged.
Disconnect/restart discards partial buckets while retaining confirmed threshold.

Enrollment selects long/short explicitly (CLI default long). A short must have
filled A sell entry and matching fills, negative szi with unchanged entry/size,
matching B buy reduce-only native Stop Market coverage and trigger no looser than
entry + ATR * multiple. Position/ledger quantities normalize to positive magnitudes;
opposite exposure, foreign entries/orders, truncated ledger and invalid protection
fail closed. Persist only after all readback validations; no exchange mutation at enrollment.

Short submit buys reduce-only IOC via existing durable UNKNOWN attempt and inward
buy-price rounding. Reconcile terminal evidence before residual retries; acceptance
never implies flat. Unknown outcomes block resend across restart. Cleanup cancels
only the enrolled stop after flatness and generation/attempt validation.

No change to eligibility, endpoints, locks, SQL schema, managed strategy entry/adds,
retry cap/deadline or protective-order lifecycle. Reject row/policy side mismatch.

Proof: policy/enrollment/gateway/runner/CLI tests, full regressions and separate
CLI replay/status with real SQLite. No live exchange execution. Rollback restores
code only after stopping management; old binaries must not read new short rows.
Alternative rejected: signed sizes throughout runner would broaden exit/storage
logic unnecessarily; retain magnitudes and normalize at gateway.
