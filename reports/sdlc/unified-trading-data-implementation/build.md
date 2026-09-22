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
