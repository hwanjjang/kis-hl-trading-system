# Post-merge investigation — 2026-09-25

Scope: AK asks whether two reported defects exist. Investigation only; no source,
commit, publication, live account or protection changes.
Revision:4b558e0da2e55c6a9321fc81ce0d5b052054e262.
Command: PYTHONPATH=. /tmp/hl-trailing-venv/bin/python /tmp/issue27-postmerge-findings.py
Executed probe bytes retained in postmerge-cancel-probe.py. Socket creation forbidden;
existing AddGateway fixtures and TemporaryDirectory SQLite only. Exit0.

1. Confirmed: initial entry quantity2 partially fills1; its remainder expires and
   cancels. Position returns PROTECTED but retains cancel_started_ms. Three days
   later authorized add.5 submits. At its own expiry, old cancel age259238999ms
   exceeds exit_deadline_ms60000, no cancel attempt targets the new add, order stays
   open, owner INTERVENTION (Entry cancellation budget exhausted). Simulated late
   add fill yields observed_size1.5, covered_size1, owner remains INTERVENTION.
   Root: owner-scoped cancellation timestamp reused by every later entry/add.
   Fix direction: persist cancellation budget per target entry/add attempt, retain
   same-target restart bounds and unknown-outcome constraints. Do not reset every
   tick or expand all cancellation budgets.
2. Confirmed: authorize queued add, request full exit, simulate completed exit and
   associated stop cleanup. Owner CLOSED; no signed add attempt. SQLite reopen and
   another supervisor step still leave tranche QUEUED/pending_adds entry. Root:
   terminal transition never retires unsent tranches; FINISHED returns immediately.
   Fix direction: terminalize only unsent QUEUED tranches with no durable attempt,
   preserve signed UNKNOWN/SUBMITTED reconciliation and terminal history. Include
   repair for already-closed owner rows so stale pending records disappear.

Prior tests verified single cancellation budgets and immediate add lifecycles, but
not a new add after an earlier cancellation cycle; no queued-add terminal-owner
cleanup scenario existed. These are missed lifecycle regressions, not a review-only
interpretation issue. Prior green suites do not disprove them.

Published defect record: https://github.com/hwanjjang/kis-hl-trading-system/issues/27#issuecomment-5827258589
Initial assessment was read-only; AK subsequently authorized implementation.
