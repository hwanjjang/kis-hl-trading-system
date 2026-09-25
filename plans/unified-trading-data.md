# Implementation plan: unified trading data

Status: original implementation sequence; PR #14 delivers the scope recorded in the [acceptance ledger](../docs/unified-data-acceptance.md). Inputs: [intent](../intent/unified-trading-data.md), [spec](../specs/unified-trading-data.md), [architecture](../docs/architecture.md#unified-trading-data-storage). The original design endpoint was local; current correction authority permits PR #14 branch push, with no merge.

## Sequence and file ownership

Implement in a task-owned branch/worktree after the user proceeds; do not combine unrelated protected-trading PR evidence or private report files. Each phase has a small reviewable acceptance boundary. File names below are proposed and may be adjusted before coding with an updated plan.

| Phase | Planned file operations | Dependency and completion evidence |
| --- | --- | --- |
| 1. Storage foundation | Add `kis_hl/data_store.py`, `kis_hl/data_migrations.py`; adapt connection creation in `storage.py`, `journal_sync.py`, `trailing_storage.py`, `managed_execution.py`, `strategy_signals.py` only where needed; add migration/connection tests | Schema ledger, stable accounts/instruments, observation/revision primitives, safe defaults, no operating-state behavior change |
| 2. Account ingestion and costs | Add `kis_hl/data_ingestion.py`, `kis_hl/data_quality.py`; extend `journal_history.py`, `journal_sync.py`, KIS client/routes; extend KIS/HL endpoint references with verified routes | Idempotent raw capture, genuine funding identity/grain, KIS statement adapters, both-side fees, metric-specific eligibility and conservation |
| 3. Existing artifact import | Add `kis_hl/data_import.py`, manifest schema and sanitized fixtures; add preview/apply CLI in a focused `data_cli.py` registered from `cli.py` | Isolated-copy import and repeat-import proof; old reports are baselines, not duplicate source facts; default operating path retained |
| 4. Market series | Add `kis_hl/market_series.py`, `kis_hl/market_ingestion.py`; adapt `daily_collector.py`, `kis_collector.py`, `reference_collector.py`, `xyz_market_collector.py` and required client wrappers; add calendar/market tests | Weekly ten-year planning/backfill, daily/minute versioning, sampled quotes/book/funding, explicit coverage/gaps and native/derived variants |
| 5. Journal and analysis consumers | Add `kis_hl/analysis_store.py`, `kis_hl/journal_exports.py`; adapt `trade_journal.py` and `operations_cli.py` with backward-readable output; update trade-journal references | Frozen source manifests, separate accounts/currencies, two unavailable KIS exact-time metrics, reproducible exports and stale-input invalidation |
| 6. Operations and cutover | Add backup/restore/retention-preview operations and tests; wire shared configurable jobs into existing journal scheduling; update `README.md`, `docs/architecture.md`, `docs/trading-operations.md`, `.env.example` only for implemented settings | Concurrency measurements, crash/backup restore, controlled same-path cutover and recovery walkthrough; no retention deletion or live order smoke |

Phases 2 and 4 both depend on phase 1; phase 3 requires account normalization; phase 5 requires the facts it consumes. Do not move every component into a generic framework at once. Existing trading ownership and eligibility rules remain authoritative. New tables should be introduced only in the phase that uses them.

## Acceptance scenarios

| Scenario | Required evidence | AC |
| --- | --- | --- |
| Same import twice, duplicate API profiles/pages | Effective fills/costs/totals unchanged; observations retained; real account identity deduplicated | AC1, AC2, AC5 |
| Identical identity with changed economics | Explicit correction/conflict, previous revision preserved, affected projections stale | AC2, AC3 |
| Same zero funding hash on multiple days | Distinct cash events, no overwrite/collision | AC2, AC3 |
| Daily funding spans close/re-entry | Exact group/account amount, individual pending; late evidence resolves once | AC3 |
| Hourly funding later returned as daily aggregate | One effective economic representation; overlapping representations cannot double charge | AC2, AC3 |
| KIS daily rows + cumulative order polls | Quantity/notional reconciliation; no cumulative quantities counted twice | AC2, AC3 |
| KIS buy fee absent in sell-profit view | Buy and sell settlement amounts reconcile net; fees included once | AC3 |
| Broker summary unit differs from field-name implication | Row currency preserved; mixed or unknown summary unit not aggregated | AC3 |
| Partial exits and reversal through zero | Quantities, gross PnL and every fee allocation conserved | AC3 |
| Exact net return with date-only timestamps | Seven return metrics eligible; exact holding metrics unavailable; no midnight/order-time substitution | AC3 |
| Missing history, transfers, corporate actions | Coverage/pending reason preserved; no fabricated cycle or capital-return metric | AC2, AC3 |
| Weekly ten-year request for newer instrument | Requested and available intervals distinct; pre-listing range explained, no manufactured bars | AC4 |
| Week with holiday, DST, year boundary, missing day, incomplete current week | Correct calendar start/end, partial flag, volume convention and completed-week eligibility | AC4 |
| Native weekly versus derived daily-to-weekly | Separate variants; only complete homogeneous daily inputs aggregate; lineage enumerates inputs | AC4 |
| Split-adjusted series revised after analysis | Old analysis reproducible; new revision cannot leak into earlier as-of backtest | AC2, AC4 |
| Same symbol different exchange/DEX/price basis | Distinct instruments/series; market rate is never account funding cash | AC1, AC4 |
| No new market update inside polling window | Sampling cadence and stale status visible; no invented tick or bar | AC4 |
| Crash between page persistence/cursor/report-file stages | Resume without duplicate facts or falsely ready output; previous report remains usable | AC2, AC5 |
| Backup under writes, isolated restore, post-cutover writes | Consistent backup; schema/integrity/financial totals verified; rollback cannot discard new fills | AC5 |
| Market writes alongside supervisor state updates | Declared workload/hardware, bounded transactions, measured latency, no lost financial state | AC1, AC5 |
| Portfolio contains KIS and tradefi but excludes Master | Account isolation, KRW/USD/USDC separation and correct external/internal transfer classification | AC3 |

Use table-driven synthetic fixtures and property-style invariants where useful; do not copy raw personal responses into tests. Preserve targeted private import reconciliation receipts separately under ignored data/.

## Verification approach and planned commands

Behavior changes follow failing regression tests, minimal implementation and refactor with tests green. Establish existing behavior before connection/migration refactors. Add tests only when the owning phase exists. The following are future commands, not results from this design turn:

```bash
python3 -m unittest tests.test_data_store tests.test_data_migrations tests.test_data_ingestion -q
python3 -m unittest tests.test_journal_history tests.test_journal_sync tests.test_trade_journal -q
python3 -m unittest tests.test_market_series tests.test_market_ingestion -q
python3 -m unittest tests.test_kis_client tests.test_hyperliquid_client tests.test_cli -q
python3 -m unittest discover -s tests -t . -q
```

Verify actual existing module names when creating phase tests. An additional functional smoke uses a fresh temporary SQLite DB and real CLI processes: import declared synthetic source files, inspect quality, generate account/combined reports, repeat import, pin an analysis, apply a correction, regenerate, back up and restore. Stubbed unit tests do not substitute for this integrated local smoke. No signed exchange action or private-data publication is needed.

A fresh-context independent verifier must challenge the implementation and migration results. PR creation/review/merge follow the user's later explicit endpoint; the current request does not authorize them. Browser tests cover report filtering, missing-value labels, exports and account/currency isolation when UI output changes.

## Migration and rollback

Use the spec's manifest-driven isolated-copy rehearsal and same-path controlled cutover. Before apply, inspect active account owners/workers, schema compatibility and verified backup. Preserve managed/trailing tables, lock paths and old report baselines. Do not copy a report DB over the operating DB or rename the live DB while a worker is active.

Rollback is a reader/feature rollback first. Restore an old database only if no later authoritative writes exist. Otherwise repair forward or replay verified new facts with explicit reconciliation. Keep immutable raw evidence and correction history in either direction. Retention remains preview-only in the first release.

## Risks, blast radius and rejected alternatives

- **What can break:** legacy CLI output, current upsert readers, metric populations, source row identity, local lock coordination, API pagination and historical market inputs.
- **Riskiest part:** selecting one effective economic representation across cumulative/daily/execution rows and mixed-grain funding, while preserving operating state during migration.
- **Rejected shortcut:** attach/copy all report DBs and sum their rows. They contain overlapping derived data, different cost semantics and incomplete precision.
- **Rejected early expansion:** exhaustive tick/L2 capture or a database server. The selected candle/snapshot workload should first prove bounded SQLite operation.
- **Proof:** source-to-ledger monetary invariants, independent settlement checks, immutable lineage, duplicate/correction/crash tests, weekly calendar fixtures and measured safe cutover/restore. No financial total may be certified merely because a legacy report happened to match.

## Definition of implementation readiness

The original design passed document and diagram checks. Current implementation evidence and remaining provider, migration and operational limits are recorded in the acceptance ledger; this design does not itself certify those outcomes.

## 2026-09-20 G1 correction sequence

1. Add tests for mixed null components in buy/sell, unequal and signed totals, historical stored facts, independent reconciliation on both evidence sets, account isolation, immutable reports and missing-source backup.
2. Share a small cost-quality helper between ingestion, journal and reconciliation. Reject proved contradictions during statement normalization; derive unresolved status at read time so old facts are covered without mutation. Backup uses readonly DataStore.
3. Update journal contract and operation docs; preserve formulas and archive bytes. Full unittest suite plus focused post-refactor checks, then separate real CLI import/reconcile/journal/export/backup/restore smoke with synthetic data and no dotenv/network.
4. Fresh-context non-builder verification before scoped commit/push. Preserve unrelated files and old failed evidence. Formal PR-review attempt limit remains unchanged; no merge readiness claim.

Risk: over-rejecting incomplete but legitimate cost detail or regressing native KIS/HL fee contracts. Retain unresolved rows rather than replacing fees with their subtotal. Do not blanket-reject every incomplete breakdown or manufacture rebate amounts. Rollback is code-only; no DB migrations or data rewrites. Pending reports may be regenerated after explicit source correction.
