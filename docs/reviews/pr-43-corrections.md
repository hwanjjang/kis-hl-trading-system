# PR 43 required corrections

Issue: [#42](https://github.com/hwanjjang/kis-hl-trading-system/issues/42).
Endpoint: pre-merge only; no merge, auto-merge, exchange order or deployment.
Reviewer requested by AK: Grok 4.7, high reasoning (explicit override of the shared
workflow's default medium effort).

## Required changes

- Count a local-protection observation gap only when both observations belong to
  the same regular execution session and the previous/current venue availability
  is open. Persist the last availability observation for restart recovery.
- Reset an unrequested stale-coverage grace period at a new session, preserving
  any already requested exit. Keep same-session gap exits and opening stop checks.
- Distinguish missing current-session date evidence from generic stale data in
  the DEGRADED reason. Holiday, instrument suspension and delayed data remain
  indistinguishable; local coverage is zero and operator investigation is needed.
- Add regression coverage and a separate CLI/SQLite restart smoke. Correct the
  obsolete Claude-specific description of the compatibility-only HL session flag.

The original PR's HL advisory session policy, filled-stop readback and read-only
KOSPI200 futures changes are retained. Main at `122c345` was integrated because
its existing replay fixture fix is necessary for the native handoff smoke.

## Recommendations deferred

| Finding | Disposition |
| --- | --- |
| Split the existing multi-topic PR | Already documented in its body; splitting is not required to correct the reproduced defects. |
| KIS portfolio/correlation admission limits | Broader risk-admission behavior, outside issue 42's explicit holding-match contract. |
| Intraday precision for entry-since window | Current date-wide rejection is conservative; no broader admission added. |
| Additional ATR close-time and CLI argument tests | No demonstrated defect from these corrections; existing assumptions remain documented. |

## Verification contract

Regression cases cover closed-to-closed downtime, persisted closed-to-open
restart, overnight/weekend open-to-open restart, stale-budget separation,
same-session observation gaps, stale quote grace, real missing-date quote parsing
and diagnostics/recovery, opening fixed-stop breach and calendar boundaries.

`python -m unittest tests.test_kis_adoption tests.test_managed_execution tests.test_managed_gateways -q`
passes 59 tests after the correction. The added
`PYTHONPATH=. python scripts/smoke_kis_handoff.py` exercises CLI parsing, SQLite,
recreated supervisors and bounded exit with an offline exchange boundary.
Full-suite, existing smoke and independent review results are recorded on the PR
against its exact final commit. No live venue behavior is claimed.

For the compact canonical task artifacts and detailed local execution evidence,
see `reports/sdlc/pr-43/` in the task workspace; it is intentionally ignored by Git.
