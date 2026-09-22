# Implementation Plan
Owner: /root; task hyperliquid-native-trailing; notebook .planning/2026-09-22-hyperliquid-native-trailing.
1. Add regression tests for action/dry-run guards, strict readback, native opt-in lifecycle, unknown outcomes and existing local default.
2. Add a focused Hyperliquid trailing wire/readback helper and trading client adapter. Preserve SDK asset resolution and serialized action lock.
3. Extend managed gateway/supervisor with a distinct trailing attempt kind, default local provider and native opt-in after entry terminality/full fixed SL. Preserve existing exits and cleanup.
4. Update instrument capabilities, operations/architecture docs and Hyperliquid skill reference tables.
5. Run relevant unittest suites and isolated real-SDK signing plus CLI/SQLite smoke. Independent verifier challenges lifecycle and contract.
Risks: response oid shape unverified live; fail closed for unknown acknowledgements. Rejected alternative: matching new open orders by timestamp/size, unsafe against foreign actions. No live probes. No cloid invented. Maximum one automatic native trail avoids watermark reset.
Dependencies: existing hyperliquid-python-sdk; isolated /tmp dependency install for verification. No runtime service introduced. No data migration. Rollback described in spec.
