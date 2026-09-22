# Independent correction revalidation — iteration 4

**Verdict: FAIL — one remaining freshness boundary.**

Candidate `sha256:3dcf4d72ecca4b1e13a41c766eb9e4bd6923e53b8da88c3eadc66574847418a7` against base `6d66b85971b7dfd5c2c7fef2ab2500cf4659f15e`. All 22 supplied file hashes matched. This is bounded distinct non-builder implementation verification, not a PR-review result or merge approval.

## Revalidated findings

- **IV3-F1 resolved:** the original native Hyperliquid PnL contradiction is rejected; no complete trade coverage is certified and the journal stays PENDING.
- **IV3-F2 resolved:** the earlier invalid segment remains PENDING without a fabricated close, while funding after recovery goes to the later FINALIZED cycle.
- **IV3-F3 partially resolved:** appending immediately before pinning now marks the old report stale. A neighboring input-boundary interleaving still fails below.

## IV4-F1 — MEDIUM — required

At `kis_hl/journal_exports.py:158`, current as-of time is selected before reading the initial max fact ID. A collector can commit a historical funding row after that time but before the watermark query. Its ID is captured in the watermark, while its knowledge time excludes it from the report. The old report has net 10, a current reconstruction has net 8, and `stale_runs` remains empty.

Reproduce with `PYTHONPATH=. python3 .planning/read_boundary_probe.py`; retained output is `.planning/read-boundary-result.json`. The probe interleaves only a valid collector append at the first report connection, using controlled timestamps. It does not mutate product code. Confidence: high.

The historical result remains valid and immutable as-of evidence. The defect is the missing current-projection regeneration signal, continuing the accepted IV3-F3 requirement. Compare the effective historical input population against pinned membership, or bind the baseline to the actual as-of population; preserve legacy reports and ignore obsolete superseded revisions.

## Actual independent checks

- Full suite: **348 passed**, 20.781 seconds; `.planning/revalidation-tests.txt`.
- Correction CLI smoke: **12 processes passed**, including preview, reconciliation, journal/export and backup/restore; `.planning/revalidation-smoke.json`.
- Original counterexample rerun: all three original triggers corrected; `.planning/revalidation-probes.txt`.
- Additional preservation probes passed: missing DB previews, existing DB bytes/mode unchanged, idle heartbeat, endpoint guard before network request, historical-as-of derived analysis accepted while current obsolete dependency rejected; `.planning/revalidation-positive.json`.
- New legacy-no-watermark regression passed in the full suite.

No product files were changed. No account APIs, credentials/private data, publication or shared state writes were used. Live broker behavior remains unverified. The broader accepted-design backlog and exhausted PR-review stage are not certified by this implementation revalidation.
