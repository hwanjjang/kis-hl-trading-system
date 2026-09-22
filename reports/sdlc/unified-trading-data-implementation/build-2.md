# Canonical data implementation build

The accepted design is implemented as additive SQLite schema, immutable raw evidence,
validated versioned account/market facts, manifest preview/apply, conservative cost
and chronology reconciliation, reproducible journal/analysis consumers, read-only
market/account collectors and a configurable CLI job runner. The exact candidate
file set and hashes are in candidate.json; change.patch is the actual scoped diff.
Unrelated protected-trading evidence and private trading data are excluded.

Storage uses a compact indexed fact table rather than unused physical tables for
every logical family. Existing operational and eligibility tables are preserved.
Current supported scope and limitations are explicit in docs/unified-data-operations.md.

Build corrections resolved partial-exit basis, export path protection, preview and
runtime import failures, transitive stale detection, optional monetary validation,
and provider-native weekly anchors. Independent findings F1–F6 and resolution
reproductions are retained. No signed exchange action was added or executed.

Current code has passed targeted tests, a separate real-CLI smoke and independent
full regression. Local deployment consists of additive import after a verified
backup and isolated rehearsal; operational receipts remain private under data/.
No commit, push, PR or merge is part of the local endpoint.

## Final incremental polling correction
Recurring minute collection starts from the last successful timestamp minus five
minutes, or 30 minutes on first run. Failures retain that cursor. Date bounds use
the instrument timezone. Explicit historical backfill defaults are unchanged.
Independent first/subsequent/failure/Korean-rollover probes and 308-test full suite
passed. F1–F7 are resolved. Final candidate.json binds the exact current files;
change-2.patch is the final diff.
