# Full review correction build

Builder: /root, OpenAI. Stable build iteration 5. Candidate file hashes and base are
in candidate.json; change.patch includes new untracked product/tests as well as the
tracked diff. Protected-trading work and private data remain untouched.

| Accepted finding | Implementation and regression |
| --- | --- |
| Claude M1 | Overseas book output2 prices/sizes plus output1 source clock; book regression. |
| Claude M2 / Codex C2 | Validated monotone KIS daily revisions, retain old keys across grouping; reject decreasing evidence and isolate datasets. |
| Claude M3 / Codex C4 | Day/side aggregates with pending shared-cost allocation; valid other days/overseas still collect. |
| Claude M4 | HL reconstruction resumes only at explicit later zero anchors; prior invalid segments and fees remain visible. |
| Claude M5 | Bounded independent-statement reconciliation with matched rows, inventory evidence, exact population coverage and atomic apply/rollback. |
| Claude M6 | Within-observation duplicate KIS identities rejected before facts; raw observation retained; cross-observation replay idempotent. |
| Codex C1 | Portable costs and settlements reconciled before ingestion; nonpositive KIS quantities rejected as validation errors. |
| Codex C3 | Journal watermarks and scope/time checks detect late facts and coverage changes; old bytes unchanged. |
| Codex C5 | Analysis traverses effective as-of dependency IDs; current stale derived bars rejected. |
| Codex C6 | KIS index price_basis=index, adjustment=raw; old mislabeled rows preserved as historical evidence. |
| Codex C7 | Canonical HL market collection explicitly mainnet-only; rejects other configured endpoints before capture. |
| Codex C8 | KIS overseas one-minute wrapper and bounded local-time cursor collection; retention remains partial. |

Operational recommendations: account/dataset SQL filtering, non-mutating status
and real schema preview, configurable account overlap/separate history-audit jobs,
worker heartbeat, partial jobs preserving success cursors, metric exclusion counts,
updated API/journal contracts and explicit broader-design acceptance ledger.

No schema DDL checksum changed. No new order path, live asset eligibility,
notification mechanism, service installation, credentials or production migration.
The existing Archify structure is unchanged (raw -> revisions -> coverage ->
projections); these are corrections/local workflow validation within that design.

Test-first core regressions failed as intended (13 tests; 9 failures/5 errors),
workflow regressions exposed missing minute/reconciliation/operational paths, and
additional source-gap/transaction rollback cases failed before their fixes. Separate
green and smoke logs are retained. The transaction regression prevents coverage
from certifying an unvalidated population during concurrent writes.

Limits: broker statements are operator-supplied trusted evidence; SHA-256 proves
byte identity, not authenticity/completeness. API entitlements/real retention are
not exercised. Nonzero starting inventory remains pending without cost basis.
Broad calendar/cutover/capital-return/storage-pressure scope is visibly outstanding
in docs/unified-data-acceptance.md. PR review is not claimed: supplementary stable
review attempts are exhausted at 10, and this work does not launch attempt 11.
