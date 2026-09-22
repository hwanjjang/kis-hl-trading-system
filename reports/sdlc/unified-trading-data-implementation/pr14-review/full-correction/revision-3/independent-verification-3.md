# Independent implementation revalidation — iteration 5

**Verdict: PASS for the bounded correction acceptance scope. No remaining confirmed findings.**

Candidate `sha256:2c84a50ec7b666d04657e4679a86c8a633940829857f6a6894ca2af21ea4835d` over base `6d66b85971b7dfd5c2c7fef2ab2500cf4659f15e`. All 22 file hashes matched before and after checks. This is distinct non-builder implementation verification, not a PR-review PASS, cross-provider gate, overall design-complete claim or merge approval.

## Resolved findings

- **IV3-F1:** independent source PnL 10 versus canonical 999 rejects reconciliation. No false complete coverage or finalized net is certified.
- **IV3-F2:** the abandoned segment remains PENDING with no fabricated close. Subsequent funding belongs to the supported recovered exposure, which finalizes correctly.
- **IV3-F3 / IV4-F1:** both append timing cases now mark report 1 stale. Old net remains 10; current reconstruction is 8. A regenerated report is fresh. Comparison against effective pinned membership removes the watermark timing gap and ignores superseded old revisions.

## Independent verification

| Check | Result |
| --- | --- |
| Full test suite | **350 passed**, 20.432 seconds |
| Correction CLI smoke | **12 real CLI processes passed** |
| Inventory CLI smoke | **7 real CLI processes passed** |
| Original three counterexamples | Corrected behavior confirmed independently |
| Initial as-of/read-boundary append | Old run correctly listed in `stale_runs` |
| Scope boundaries | Other account and future event do not falsely invalidate old report |
| Late coverage | Old report becomes stale; rebuilt report stays fresh |
| Corrections | Prior revision run stale; current effective revision run fresh |
| Legacy watermark fields | Missing/obsolete watermark fields do not suppress detection |
| Other preservation | Read-only previews/status, idle heartbeat, pre-request endpoint guard, historical/current derived-input checks pass |

Commands and full structured results are in `verification-3.json`. Reproducible verifier scripts and outputs:

- `.planning/revalidation_probes.py` → `.planning/revalidation3-probes.txt`
- `.planning/read_boundary_probe.py` → `.planning/revalidation3-read-boundary.json`
- `.planning/freshness_boundaries.py` → `.planning/freshness-boundaries.json`
- `.planning/positive_probes.py` → `.planning/revalidation3-positive.json`
- `.planning/revalidation3-tests.txt`, `.planning/revalidation3-smoke.json`, `.planning/revalidation3-inventory-smoke.json`

The other accepted correction themes remain covered by prior unchanged-source inspection and the rerun full regressions: cost/settlement validation, positive quantities, duplicate ambiguity, mutable KIS snapshots and grouped pending costs, scoped journals, book/index/minute semantics, network guard, read-only schema/status, overlap/audit jobs, heartbeat and metric exclusions. No new confirmed defect was found in this bounded revalidation.

## Limits

No product edits, account APIs, credentials/private data, publication or shared workflow writes. Tests use synthetic data and temporary SQLite; broker entitlements, live behavior and historical depth remain unverified. Concurrency probes force precise interleavings and do not claim a production-load benchmark or globally atomic read snapshot. Broader outstanding design work and PR-review/merge gates are outside this result.

Verifier: `/root/codex_full_review_1`, OpenAI Codex based on GPT-6, distinct non-builder. Exact runtime backend identifier and reasoning effort are not surfaced by this context.
