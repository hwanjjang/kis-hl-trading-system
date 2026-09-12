# Protected trading implementation plan

Owner notebook: [.planning](../.planning/2026-09-12-protected-trading/task_plan.md).
Follow the ordered slices and behavioral scenarios in
[multi-venue-protection](multi-venue-protection.md); exclude notification delivery.

1. Add exact KIS reads and guarded writes, explicit instrument routes and capability
   data; test vendor fields, environments, failure responses and pagination.
2. Add immutable fill/cost facts, coverage tracking and cycle reconciliation; test
   external-only, overlapping sync, missing opening/costs, mixed attribution and
   legacy records without fabricating per-fill prices from cumulative summaries.
3. Add a configurable persistent 3h scheduler and manual sync entry point.
4. Add durable execution/protection ownership and account supervision, with
   bounded UNKNOWN recovery and native/local provider readiness before entry.
5. Wire CLI and future strategy contracts without inventing trading rules or alerts.
6. Exercise unittest plus separate offline local integration smoke, reconcile docs
   and diagram claims, obtain independent verification; preserve secrets.
7. Commit/push the tested candidate, create PR and obtain eligible independent
   review. Retain detailed local evidence and concise PR result; do not merge.

Rollback disables new entries/jobs while preserving raw facts and native orders.
Additive migrations retain old rows and snapshots. Never delete fill history.
