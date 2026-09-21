# Claude and Codex full-review correction evidence

The active candidate is **revision-3**; earlier directories preserve failed
candidates and actual Red/Green/independent-verification history. They are not
current approval claims. Source base: `6d66b85971b7dfd5c2c7fef2ab2500cf4659f15e`.

- [Current source hashes](revision-3/candidate.json)
- [Current build](revision-3/build.md)
- [Current test scenarios/results](revision-3/test-results.json)
- [Current self-verification](revision-3/self-verification.md)
- [Independent acceptance PASS](revision-3/independent-verification-3.md)
- [Initial correction mapping for all twelve accepted groups](build.md)
- [Broader implementation acceptance](../../../../../docs/unified-data-acceptance.md)
- [PR-review iteration limit](review-limit.md)

Accepted input findings are in the [Claude/Fable assessment comment](https://github.com/hwanjjang/kis-hl-trading-system/pull/14#issuecomment-5741654696)
and [three Codex review assessment](https://github.com/hwanjjang/kis-hl-trading-system/pull/14#issuecomment-5741799141).
There are twelve unique mandatory groups (six Claude, eight Codex, two overlaps).
This correction also covers scoped reads, non-mutating status/schema preview,
overlap/audit jobs, heartbeat and metric exclusions. Cosmetic broad refactoring,
destructive schema cleanup and unproven API claims were not accepted fixes.

Final local checks: 350 tests, 34 focused post-refactor tests, and 19 real CLI
subprocesses in two functional smokes passed. Independent verification reports are
retained per candidate. Reconciliation gross-PnL matching and recovery funding
exposure were additionally corrected following independent failures. Freshness now
compares the current effective input population rather than max-ID watermarks,
covering both concurrent append boundaries and historical as-of selection without
invalidating fresh reports solely because superseded revisions exist.

The ordinary PR-review stage has exhausted ten attempts. Independent implementation
verification is a separate stage and does not confer PR approval or merge authority.
No live account calls, production data migration, order actions, permission changes,
service installation or merge were performed. Private source data remains ignored.
