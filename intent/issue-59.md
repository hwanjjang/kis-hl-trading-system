# Issue 59: warning-only account-read outages and visible intervention blockers

Source: https://github.com/hwanjjang/kis-hl-trading-system/issues/59 (body and the 2026-10-13 recurrence comment) and AK's explicit pre-merge request on 2026-10-13.
Owner: Claude Code. Route: implementation / behavior / pre-merge.

A temporary account-read outage currently latches a liquidation request after three failed snapshots or `protection_grace_ms`. Once reads recover after `exit_deadline_ms`, owners with consistent exposure and live native protection stay in `INTERVENTION` forever. Diagnostics then hide that deadline blocker behind the first outage summary. AK decided on 2026-10-09 that an account-read failure is an operational warning, not a sell signal, for both Hyperliquid and KIS.

## Scope and authority

In scope: change the shared supervisor so read outages are warning-only; add deduplicated outage/recovery notifications to a durable outbox that Hermes delivers and acknowledges; expose first cause, current blocker, read health, paused local supervision, exit provenance and budgets separately; make `order recover` explain exhausted budgets; add an exact, scoped and explicitly invoked withdrawal command for legacy read-outage exit latches; update the operations docs; add tests and smoke. Then commit, push, open/update a PR, run CI and a different-provider review, and apply corrections.

Not authorized: live orders, running live commands, owner recovery or withdrawal on operational databases, SQLite edits, service restart, deployment, merge, auto-merge, merge-queue entry, permission changes. Withdrawing the live SP500/AVGO latches stays a separate AK decision.

## Acceptance criteria

- AC1: HL and KIS. Three consecutive failures, plus an outage longer than both protection grace and exit deadline, including a restart, create no exit request, flag or deadline and send no order. Fresh consistent recovery resumes authorized protection without duplicate SL/TS. Real protection hits and independently authorized exits keep their existing policy, including during an outage.
- AC2: An outage records one deduplicated sanitized warning. Fresh consistent recovery records one recovery notice. Both are delivered through a Hermes list/acknowledge path. Repeated polling, restart and failed-delivery retry are covered. Notification failures never cause liquidation.
- AC3: A later transient failure followed by successful readback keeps the first cause and does not hide the current exhausted-budget blocker. Status exposes read health and paused local supervision separately. Error classification is structured and contains no secrets.
- AC4: Explicit recovery of an exhausted-budget owner explains why unchanged-budget recovery cannot proceed. Generic identity/foreign-order intervention and UNKNOWN no-resend behavior stay fail-closed, without automatic renewal of authority or budgets. Legacy read-outage latches report their provenance. They can only be withdrawn through an exact, scoped command, never by bulk clearing.
- AC5: The managed-execution, gateway, KIS adoption and native-trailing tests pass. `docs/trading-operations.md` documents the following: warning-only outages, the risk of impaired local supervision, notification and recovery behavior, legacy-latch handling, and the difference between state transitions and polling events.

## Risks and open questions

- Local-only protection (KIS local SL, HL local trailing backup) is not enforced while reads fail. It cannot fire during an outage, and the outage no longer forces an exit. This is AK's accepted risk. It is disclosed in status, notifications and the docs.
- A single transient read blip produces one warning and one recovery notice. Notification volume under real HL error rates is unverified.
- The historical HTTP status of the October outages is unknown. The new classification applies only to future failures.
- Hermes delivery wiring (cron/agent prompt) lives outside this repository. Only the CLI contract is delivered and tested here.
