# Issue 58: journal every fill at execution time and report journal status

Source: https://github.com/hwanjjang/kis-hl-trading-system/issues/58 (body), the 2026-10-13 decision comment ("Response to Phase 1 decisions and sequencing", D1/D2/S2) and the 2026-10-14 revised completion-criteria comment. AK's session instruction on 2026-10-14 started implementation from the latest main through a PR ("2번부터 진행").
Owner: Claude Code. Route: implementation / behavior / pre-merge. Base: `origin/main` `513364d`, which includes #61 (shared outbox), #62 and #63.

Position-change journals are written only when someone runs an account sync by hand. Neither supervisor requests a sync after it observes a fill, and the documented policy forbids scheduled callers. As a result, fills went unjournaled until a manual sync, and an external Hermes cron is now a stopgap. AK wants a journal entry for each fill, a notification and a status report, with the repository as the single sync caller.

## Decisions consumed

- **D1:** use one repository-owned SQLite outbox for notifications: the existing `managed_notifications` from #59. Hermes delivers and acknowledges through the existing `supervisor notifications` / `notification-result` path. Deduplicate journal notifications by `journal_id`. Do not claim exactly-once external delivery.
- **D2:** run the periodic fallback as `market collect` account jobs (HL 300 s; KIS 3,600 s during execution sessions). Fill-triggered requests are durable and asynchronous after the supervisor state commit. A Hermes schedule calls the same read-only `data journal-status` for the daily summary after the US close. Activating the worker is a cutover step, not part of this change.

## Scope and authority

In scope:
- Record a durable, coalesced sync request when a supervisor observes a fill, after its state commit.
- Process requests in the `market collect` worker with bounded ranges, retry and backoff.
- Enqueue deduplicated journal notifications for new journals from either path.
- Add the read-only `data journal-status` command and an explicit daily-summary enqueue.
- Update the policy docs, README, architecture and the trade-journal skill, plus a CLI manual with actual usage captures.
- Tests and smoke, then commit, push, PR (`Refs #58`), CI, a different-provider review and corrections.

Not authorized: live orders; changes to operational databases; service installation, restart or deployment; removing the Hermes cron or `journal_auto_sync.py`; merge, auto-merge or merge-queue entry; permission changes. The test-account live smoke and the production readiness, delivery and cutover checks from the revised criteria are post-merge steps and need separate approval.

## Acceptance criteria

- **AC1 (fill-triggered request):** a fill observed by an HL or KIS supervisor (entry, add, protective or trailing exit, manual close, or flat transition) records exactly one pending sync request for that venue/account, after the supervisor state commit. Repeated fills coalesce into one pending request. A failure to record the request does not change supervisor state, protection or order handling.
- **AC2 (processing, retry, fallback):** the `market collect` worker processes due requests with a bounded overlap range. On failure or timeout it records the failure and retries with capped exponential backoff, and a later success clears the failure. Account jobs at the configured fallback interval journal unowned fills. Repeated syncs create no duplicate journals or notifications.
- **AC3 (notifications):** each successful sync that creates journals enqueues one outbox notification per batch. The message gives instrument, change type, signed quantity, price, KST execution time and source precision. A `close` shows realized PnL and return % only when the cycle is finalized and otherwise labels them pending. KIS DAY precision is labeled, never given a fabricated time. Each `journal_id` is notified at most once, and Hermes lists and acknowledges these notifications through the existing path.
- **AC4 (status report):** the read-only `data journal-status` reports, for HL and KIS accounts:
  - open positions
  - today's (KST) journal entries
  - completed cycles and the nine trade-journal statistics, pending when not finalized
  - pending items (unanchored inventory, missing costs, partial coverage)
  - last successful sync and any sync failures for each account

  The daily summary uses the same output, enqueued by an explicit flag at most once per KST day.
- **AC5 (docs and safety):** the full offline suite and all CI smoke scripts pass. No new order, cancel or transfer code path is introduced. `docs/unified-data-operations.md` replaces the "user or agent initiated" policy with the fill-triggered and fallback policy, its latency bounds and its failure behavior. README, `docs/architecture.md`, the trade-journal skill and the `AGENTS.md` ownership table are updated where ownership changes. A CLI manual with actual usage captures and a PDF is delivered.

## Risks and open questions

- Journals depend on a running `market collect` worker. The decision comment found none on the operations host, so without cutover, requests accumulate and are visible as pending in `journal-status`.
- HL fills can be observed after their exchange time. The bounded range starts before the supervisor's previous observation, and the job's one-day overlap is a second net.
- Routine syncs leave cycles `PENDING` (HL cash coverage, KIS trade coverage). Notifications and statistics show pending values until Phase 2 work certifies coverage.
- Delivery is at-least-once: a crash after Telegram send but before acknowledgement can resend. This is the existing outbox contract and is disclosed, not hidden.
- PR #57 changes `managed_execution.py` and `operations_cli.py`, and whichever PR merges second must integrate. The fill hook is kept small and outside the take-profit code.
