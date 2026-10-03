# Issue 51: plan
Owner root; 2026-10-03; revision 1; PROCEED. Inputs: issue-51 intent/spec revision 1.
Execution notebook: .planning/issue-51 (root owns it); artifact index: reports/sdlc/issue-51.

1. Import only existing trailing tests from beefy-turkey; run on unchanged main and retain Red.
2. Port scoped trailing.py, trailing_runner.py and CLI hunks. Add missing safety/rounding cases.
3. Update README/operations, add short replay and separate executable CLI/SQLite smoke.
4. Run focused then full suite, smoke, content checks; capture actual CLI usage/results
   in an editable manual and visually checked PDF. Keep maintained assets under docs/operations.
5. Commit/push branch, create PR linked to #51; independent Claude review at medium/auto,
   correct Required findings, check exact-head CI and no armed automatic integration.
6. Complete pre-merge readiness; never merge, enqueue or enable auto-merge.

Scenarios (also machine-readable in reports/sdlc/issue-51/user-scenarios.json):
- S1 (AC1/AC4): Operator replays short fixture offline, then reads status. Prerequisites:
  Python runtime, fresh temporary SQLite. Steps: replay short JSONL; query status;
  inspect threshold and intent. Expected: low 92, threshold 104 -> 96, PAPER_EXIT,
  persistent intent and no attempts. Failure: wrong side, upward threshold or any network.
- S2 (AC2/AC5): Operator enrolls a filled protected short. Prerequisites: eligible
  asset, complete sell fills, matching exposure/entry and owned buy native stop.
  Steps: select --side short; provide entry/stop IDs and explicit budgets; enroll
  paper; inspect persisted direction/protection. Expected: protected short, no order
  mutation. Wrong entry, stop, exposure, ownership or coverage rejects with no row.
- S3 (AC3): Manager exits after rebound, reconciles partial fill and restart.
  Prerequisites: live-shaped local fixtures with mocked venue; no real credentials.
  Steps: cross threshold; inspect buy IOC; lose response; restart; prove no resend;
  confirm terminal partial fill; exit residual; prove flat then owned stop cleanup.
  Expected: inward buy rounding, retained intent, bounded retry and scoped cleanup.
  Failure: unknown resend, increased/reversed position, foreign generation or stop mismatch.

S1 uses additional real CLI smoke and CLI/policy tests. S2 uses gateway enrollment
and CLI parser tests; S3 uses gateway/runner tests. Reuse all long and managed
regressions from current main. Update manual sections for S1/S2 and limits for S3.

Risk/blast radius: local manager only; direction bugs could close wrong generation,
so fail-closed guards and negative tests precede adoption. No new SQL migration.
Rollback requires manager shutdown; old code cannot manage short snapshots.
Rejected alternative: replacing runner's magnitude contract with signed sizes.
No new structure/flow diagram: unchanged lifecycle with symmetric direction predicates.
No shared read-only artifact checker found; report absent enforcement, use git diff
--check and inspect staged/outgoing content without adding unrelated tooling.
Retain selected logs/manual in docs/evidence and docs/operations, generated state in
ignored reports. CI logs alone are not durable evidence. Review receipts go in PR.
