# PR #14 review — Fable 5.1 (medium)

- PR: https://github.com/hwanjjang/kis-hl-trading-system/pull/14 (`feature/unified-trading-data` -> `update-readme-md`)
- Head reviewed: `76d22d4a1aa0ee2ce804bae1aa2d074af5793a51` (verified equal to remote head via `gh api`)
- Stacked base: `623b33392af24c9efeb7acf1c364251e9d7d2ae3` (verified equal to remote `base.sha`); PR #13 content excluded
- Reviewer: Claude Fable 5.1, model id `claude-fable-5-1` (settings.json `claude-fable-5-1[1m]`), `CLAUDE_EFFORT=medium`, autonomous non-interactive session in detached worktree `/root/.local/state/kis-hl/reviews/pr14-fable-51`
- Comment: https://github.com/hwanjjang/kis-hl-trading-system/pull/14#issuecomment-5651081887
- Date: 2026-09-13. Scope: this diff only; no code changes, commits, push, orders, credentials or vendor API calls. Probes wrote only temporary synthetic SQLite files under `/tmp`.

## Checks actually performed

| Check | Result |
| --- | --- |
| Remote head/base verification (`gh pr view`, `gh api pulls/14`) | head and base SHAs match assignment; 0 existing comments before posting |
| Read AGENTS.md, CLAUDE.md, spec, plan, ops doc, independent-verification.md, candidate.json, test-results.json, skill reference diffs | done; historical reports treated as evidence only. Raw `*.log` files referenced by reports are not in the checkout and were not read |
| Read all new/changed `kis_hl/` modules and `tests/test_unified_data.py` in full | done (~1.4k lines) |
| `python3 -m unittest discover -s tests -t . -q` | PASS, 308 tests, 26.6 s |
| Synthetic probe P1: KIS statement buy 3 / sell 10 / buy 7 with complete coverage | two FINALIZED cycles incl. a fabricated `short` cycle (F-1) |
| Synthetic probe P3: same sequence on an HL scope with `position_before` | correct long+short reversal, fees conserved (1.3 + 1.7) |
| Probe P2: WAL/SHM file permissions with open connection | all `0600`; no finding |
| Probe P5: `data status --db <fresh path>` | creates DB and applies migration (F-4) |
| Code inspection: `fact()` correction identity, `facts()` as-of selection, `pin()`/`status()` transitive stale, `effective_funding`, `run_due` lock + clocks, HL candle duration/`T+1`, KIS weekly cursor, backup/restore guards, export atomic rename | no additional defects found |
| Live vendor field names (TTTC8715R/CTOS4001R output fields, HL `T` semantics) | NOT verified (no network by policy); relies on skill references |

## Findings

### F-1 — Must Fix — HIGH — accounting
`kis_hl/journal_exports.py:60-70`. The KIS guard against opening a short position only fires when `position == 0` before the fill. A KIS sell larger than the tracked long inventory closes the tracked quantity and then falls into the generic `position==0` branch inside the `while remaining` loop, which opens a `side='short'` cycle for the remainder. A later buy "closes" that short and both cycles reach `FINALIZED` with `net_return_pct`, so they enter the nine statistics.

Trigger (probe P1): statement rows `buy 3 @100`, `sell 10 @120`, `buy 7 @110` on `kis:X`, `coverage complete`. Output: cycle 1 long FINALIZED net 58.7; cycle 2 **short FINALIZED** net 68.3, `win_rate_pct=100`, `quality_findings=[]`, `coverage_status='verified'`. Reality: the account held at least 10 units before the first covered buy; the "short" is fabricated and the long cycle's basis is wrong.

Why mandatory: the code's own invariant (line 60) says a KIS sell from flat is an `opening_inventory_gap`; the zero-crossing path bypasses it and produces finalized, statistically counted results with no quality finding. Both `kis_overseas_trans` (no `position_before`) and unresolved `kis_domestic_bundle` days reach this path. Fix shape: apply the KIS check to `remaining` after the closing segment (or whenever `position + change` would go negative for `kis:` instruments) and emit `opening_inventory_gap`.

### F-2 — Recommended — MEDIUM — source completeness
`kis_hl/journal_exports.py:110-117` and `kis_hl/data_ingestion.py:48-63`. Coverage verification for a cycle starts at `opened_ms`; nothing establishes that the account was flat before the first KIS buy. `kis_overseas` never sets `position_before`, and `domestic_bundle` only sets it when the first day's opening quantity is exactly 0. `day_end_quantity` is stored but never read by `account_cycles`. Result: a KIS buy that is really an add-on to pre-existing inventory finalizes as a fresh cycle with the wrong entry basis (probe P1 cycle 1). Recommendation: require an inventory anchor (a position/balance snapshot or `day_end_quantity` reconciliation) before finalizing KIS cycles, or mark them `inventory_unanchored` pending. Optional because the ops doc already says KIS chronology "require[s] reconciliation", but the current output labels such cycles `verified`.

### F-3 — Recommended — LOW — scheduler concurrency / docs
`kis_hl/data_jobs.py:96` uses `account_lock`, which is `LOCK_NB` and raises `RuntimeError('Account has another execution owner')` (`kis_hl/execution_lock.py:31-33`). A second `market collect` process therefore exits, and the `while True` loop in `data_cli.py:88-91` does not catch it. Fail-closed, no duplicate runs, but `docs/unified-data-operations.md:114` says the lock "serializes job runners", which implies waiting. Either catch and wait in the poll loop or reword the doc.

### F-4 — Recommended — LOW — restore/migration safety
`kis_hl/data_cli.py:43-44`: `data status` constructs `DataStore`, which creates the file and applies migration 1 to whatever `--db` path is given (probe P5). The ops doc presents `status` as inspection and only states that migrate preview does not create a database. A mistyped `--db` silently creates a migrated store; consider a read-only status path or an explicit note.

## Not flagged
- Documented deferred items (retention deletion, capital returns, KIS overseas minute history, always-`partial` HL funding coverage from sync) match the stated guarantees.
- Correction identity, as-of revision selection, transitive stale propagation, mixed-grain funding quarantine, backup/restore/export guards: inspected, consistent with tests.

## Limits
- No live vendor calls; KIS/HL field semantics accepted from skill references.
- Raw execution logs cited by the reports are not in this checkout.
- One review pass; no re-review of unchanged code.
