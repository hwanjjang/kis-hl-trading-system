# Issue 49 specification

Input: intent/issue-49.md; original deployed profile script and issue follow-up.

Keep the current 540000 ms aggregation, 15000 ms finalization grace and 4900-minute conservative retention bound. Validate each required constituent interval and finite positive high/close/bid. Reject incomplete coverage without synthesizing bars. Retain generation/high/threshold semantics and the unchanged bid-versus-threshold advisory.

`kis_hl.advisory_ts` owns deterministic aggregation, allowlisted failures, SQLite alert/bar state and per-symbol observation. A thin versioned script calls its scheduling entrypoint. Deployment uses a non-secret local JSON config for repository root, expected account and existing owner IDs; no new credentials are copied.

Use existing `bars` and `alerts` tables unchanged and add `diagnostics(coin PRIMARY KEY, payload TEXT)`. Store only operation/reason/explanation, safe bucket/missing-minute timestamps, observed_ms, last_success_ms, prior watermark and covered-through, with separately reported protection status. Stable reason codes cover coverage_gap, retention_limit, exposure_mismatch, entry_evidence_missing, invalid_bid, invalid_schema, owner_missing, owner_identity_mismatch, configuration_mismatch, read_unavailable and unexpected_failure. No exception text or arbitrary payload enters diagnostics.

Read owners inside per-symbol boundaries. Shared account reads are cached as success or failure; a shared failure degrades all affected symbols explicitly. Validate all necessary evidence before bar-state commit. Failed observations never change bars, including failures after aggregation. Successful observations transition from a prior degraded reason to verified exactly once. Closed exposure ends observation explicitly and cannot falsely certify recovery. Protection presence is independent of advisory health and scheduler success.

Operational DB uses SQLite mode=ro. Only HyperliquidInfoClient reads are exposed: clearinghouse state, frontend orders, fills, candles and book. No trading client/SDK import or signed route is introduced. Diagnostics and reports never print raw readback. State migration is additive and existing legacy error values receive verified recovery only after actual validation.

Testing: complete/gap/boundary-invalid/duplicate/malformed/NaN fixtures, stable classifications and safe errors, failed-bid atomicity, owner failure isolation, real info-client recording transport allowlist, scratch SQLite CLI smoke and exact deployed-file hash/read-only verification. Rollback restores the original profile wrapper; additive diagnostics can remain.
