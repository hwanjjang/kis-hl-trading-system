# Implementation plan

Owner: main (Claude Code). Notebook: reports/sdlc/issue-28/. Upstream:
intent/issue-28.md, specs/issue-28.md. Endpoint pre-merge. Branch
feat/issue-28-partial-take-profit from 5bf175c.

1. Tests first in tests/test_take_profit.py (stub gateway reused from
   tests/test_managed_execution.py): quantity table, below-minimum, duplicate and
   reused decisions, UNKNOWN restart, lifecycle with reopen, competing SL fill,
   profitable TS full exit, add blocking, KIS rejection, CLI. Observe Red.
2. managed_execution.py: request_take_profit, add guard in enqueue_add, supervisor
   `_take_profit` step, supersede rule, TP-aware full-exit wait and flat cleanup.
3. managed_gateways.py: HL IOC for take_profit, per-attempt TP fills; KIS rejects.
   conditional_add.py: owner TP guard. operations_cli.py: `order take-profit`.
4. scripts/smoke_take_profit.py: offline CLI + SQLite + supervisor smoke with a stub
   HL info/trading client through the real ManagedHyperliquidGateway, no network.
5. Docs: docs/trading-operations.md exit-quantity policy, README CLI usage.
6. Run tests (changed scope + full suite), smoke, `git diff --check`; commit, push,
   PR; cross-provider review (Codex) and corrections until PASS; merge-ready report.

User scenarios: reports/sdlc/issue-28/user-scenarios.json (S1-S4).
Rollback: revert the commit; persisted `take_profit` fields are additive JSON and
ignored by older code; never cancel protection or replay UNKNOWN orders.
Blast radius: managed HL owners only when a TP is requested; no change otherwise.
