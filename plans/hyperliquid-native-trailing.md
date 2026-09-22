# Implementation Plan
Owner: /root; task hyperliquid-native-trailing; notebook .planning/2026-09-22-hyperliquid-native-trailing.
1. Add regression tests for action/dry-run guards, strict readback, native opt-in lifecycle, unknown outcomes and existing local default.
2. Add a focused Hyperliquid trailing wire/readback helper and trading client adapter. Preserve SDK asset resolution and serialized action lock.
3. Extend managed gateway/supervisor with a distinct trailing attempt kind, default local provider and native opt-in after entry terminality/full fixed SL. Preserve existing exits and cleanup.
4. Update instrument capabilities, operations/architecture docs and Hyperliquid skill reference tables.
5. Run relevant unittest suites and isolated real-SDK signing plus CLI/SQLite smoke. Independent verifier challenges lifecycle and contract.
Risks: response oid shape unverified live; fail closed for unknown acknowledgements. Rejected alternative: matching new open orders by timestamp/size, unsafe against foreign actions. No live probes. No cloid invented. Maximum one automatic native trail avoids watermark reset.
Dependencies: existing hyperliquid-python-sdk; isolated /tmp dependency install for verification. No runtime service introduced. No data migration. Rollback described in spec.

## PR correction plan (2026-09-22, owner /root)
1. Add failing regressions in tests/test_native_trailing.py for rejection without exit, fixed-SL loss after rejection, waiting across grace/restart then activation, distance-specific rounding before entry (including zero), and parser syntax versus semantic mismatches.
2. Add shared precision normalization/validation and structured condition parsing in hyperliquid/trailing.py; reuse validation in client.py. Expose metadata decimal tick in managed_gateways.py. Persist normalized distance in supervisor preflight; retain backwards handling for in-flight rows.
3. Correct supervisor native transitions without changing local provider behavior. A dedicated native-intervention marker permits fixed-SL monitoring and explicit exits; generic reconciliation errors clear this marker and retain existing freeze behavior. Open waiting is not active coverage and is not itself an exit reason.
4. Extend scripts/smoke_native_trailing.py with actual gateway/supervisor/SQLite lifecycle replay through readback and restart, with exchange boundary simulated. Keep real SDK signature recovery and CLI paper preview. No network or funded account.
5. Update operations/API references, refresh sequence diagram, run focused Red/Green plus full regression and separate smoke, then assign independent verification of exact candidate. Commit/push the existing PR and publish one concise evidence/status comment.
Risk: allowing native intervention to bypass generic freeze could mask unrelated reconciliation errors. Test that malformed snapshot still freezes and no duplicate trailing is sent. Rejected alternative: accepting all app strings as protection; percent/activation mismatches stay rejected. No schema migration; added JSON fields are optional for prior records. Rollback must retain known owned protection and requires operator reconciliation, not automatic provider migration. Scope is corrective PR update, not merge readiness or live validation.
