# Account audit contract

Keep the CLI-first architecture and existing schema. Introduce `data audit-collect`,
`data audit-compare` and `data audit-apply`. Source bundles and reports are private
JSON at new paths, mode 0600, with version and SHA-256 identities. Each bundle
selects one explicit venue/environment/native account and time range. Capture
uses existing read-only clients and normalizers, preserves header-free source
responses and decoded adapter inputs, and does not open the operational DB.
KIS uses complete local-date boundaries and bounded profit query windows. Provider
retention and incomplete collection remain explicit; pagination is not certification.

Compare supports multiple bundles with distinct accounts. Normalize native input
again, detect identical/additional/changed/absent facts within the capture range,
and report same-day funding equivalence only with matching sample count and amount.
Missing records, inconsistent costs, ambiguous representations and contradictory
inventory block apply. A shorter source range does not delete older history.
Unknown opening inventory is reported, never silently asserted zero. KIS matching
uses its daily symbol/side grain when a cumulative order identity matures.

The report binds bundle content and operational DB path/account state, including
revisions and coverage. Apply verifies the exact reviewed report hash, re-derives
the diff under an immediate SQLite transaction, rejects drift and unresolved
findings, and requires `--allow-corrections` for existing fact changes. It imports
source evidence and appends revisions; no facts or old reports are deleted.
Successful application records a durable digest-keyed receipt in collection_runs.
Reapplying that report returns its existing receipt without new facts or reports.
Optional `--journals` generates each selected account journal plus a combined
journal in the same transaction. All reports retain existing pending coverage,
currency and funding rules. This workflow does not replace independent statement
certification via `data reconcile` and never certifies lifetime completeness.

Verify with synthetic native source clients, real SQLite, CLI subprocess smoke,
stale-report/digest/correction/rollback/replay tests and existing regression tests.
No operational database or private fixture enters tests or Git. Hashes bind local
bytes, not broker authenticity; user-controlled source files remain explicit input.
