# Completed-Trade Record Contract

## Record boundary

One record represents one completed position cycle:

```text
flat -> first entry -> optional adds/reductions -> final exit -> flat
```

Do not add an open position to realized statistics. If a strategy treats independent
lots as independent decisions, record those lots separately and state that convention;
do not mix lot-level and position-level records in one strategy population.

## Required inputs and derived values

`TradeJournalRecord` stores venue, symbol, strategy, side, open/close timestamps,
average entry/exit prices, quantity, fees, realized PnL, realized return percentage,
holding days, outcome, and notes.

When `realized_pnl` is omitted, the repo calculates:

```text
long/buy  = (exit_price - entry_price) * quantity - fees
short/sell = (entry_price - exit_price) * quantity - fees

realized_pnl_pct = realized_pnl / (entry_price * quantity) * 100
holding_days = (closed_at_ms - opened_at_ms) / 86_400_000
```

Holding days are elapsed 24-hour days, not inclusive calendar days or exchange session
counts. A same-timestamp open and close therefore has `holding_days == 0`.

When `realized_pnl` is supplied explicitly, it is authoritative for outcome and return
percentage. The caller must ensure it is net of all intended fees, taxes, funding, and
other execution costs; `fees` is stored but is not subtracted a second time.

## Partial fills

The legacy `journal add` CLI accepts one entry price, one exit price, and one
quantity. The account-wide `journal import/sync` path stores immutable source fills
and derives flat-to-flat cycles. For manually aggregated partial fills, provide
quantity-weighted average prices:

```text
weighted_average_price = sum(fill_price * fill_quantity) / sum(fill_quantity)
```

If entry and exit quantities differ because of transfers, residual dust, or incomplete
reconciliation, do not fabricate a completed record. Resolve the position boundary or
provide an exchange-reported net realized PnL with an explanatory note.

## Compatibility fields and snapshots

- `adjusted_outcome` is a legacy manual classification field. Keep it readable and
  writable for existing rows/commands, but it does not affect the nine required
  statistics.
- `stats_json` is the statistics snapshot that existed when a row was inserted. Do not
  rewrite historical snapshots implicitly. `journal stats` recalculates current
  aggregate statistics from raw record fields.
- Older snapshots may contain count-ratio semantics from before issue #4. Treat the
  raw trade fields as authoritative when recalculating.

## Filtering

`journal stats` can filter by symbol and strategy. Use the strategy filter for edge and
risk decisions. An unfiltered report is useful as an account overview but should not be
used to claim that every included strategy has the same expectancy.

## Account-wide source ledger

`journal_sync.py` stores account/environment-scoped execution revisions, cash costs,
coverage intervals, pending/finalized cycle revisions and immutable statistics
snapshots. `journal_history.py` reads HL native fills/funding and retains KIS
cumulative order snapshots. KIS summaries do not establish exact fill timestamps
or complete costs: import a sourced execution/cost statement before finalization.

The default sync interval is 10800 seconds, configurable and persistent. Publication
is independent of order completion. Missing opening history/costs, retention gaps,
ambiguous equal-time ordering or legacy overlap remain pending. A correction can
supersede cycle boundaries; new snapshots use the entire corrected effective set,
while previous snapshots are retained. Partial reversals split at zero and conserve
quantity/fees. Reports separate currencies and mixed/unassigned strategy populations.
No formula in the nine-statistic contract changes. See the operations guide for the
JSON statement schema and explicit coverage/attribution responsibilities.

Automatic Hyperliquid sync permits append-only enrichment from unknown attribution
when an exact native order match becomes available. Economic fields must remain
identical; known attribution conflicts require an explicit correction. Reobserving
unknown attribution never removes existing evidenced attribution.

The scheduler records every collection attempt and its reason separately from
last successful collection and verified execution/cost coverage. Incomplete or
failed attempts wait the configurable interval; explicit sync may retry sooner.

## Canonical data journals

`data journal --accounts ...` reads `fact_revisions` and freezes exact inputs in
`analysis_runs/analysis_inputs`. It preserves existing nine-statistic formulas;
DAY records may contribute to the seven return metrics when monetary and sequence
evidence is complete, while exact holding-day statistics remain unavailable.
KIS dated sell cost basis and ending inventory may establish a unique sequence;
order time alone does not. Partial exits use remaining inventory basis before a
later add. Hyperliquid builder fees are components of total fees, not extra debits.
Funding daily/hourly overlap requires explicit equivalence; ambiguous allocations
remain pending per cycle while observed account/currency totals stay separate.
`net_booked_pnl` describes observed source activity; coverage status must accompany
it and it is not a lifetime or deposit-adjusted portfolio return. Existing legacy
`journal` commands remain compatibility readers/writers for their older tables;
canonical reports never sum those projections as additional trades.

The canonical `kis-inventory-v1` policy requires a source-backed zero opening
position or continuous inventory from a previously anchored KIS cycle. Trade-range
coverage is not an inventory anchor. Unanchored cycles cannot contribute confirmed
returns or completed-position statistics. A KIS oversell is an inventory gap and
must be detected before any part is finalized; it never creates a short cycle.
Contradictory DAY ending holdings invalidate cycles overlapping that day after all
same-day events have been processed. Earlier verified cycles and genuine
Hyperliquid reversals remain supported. New runs pin this inventory policy;
historical report IDs remain frozen, and raw facts/fees are never rewritten.


Portable statement costs are disjoint included components, including explicitly
signed rebates. Fully known components must sum to total_cost; any supplied
settlement must reconcile it. Proved contradictions reject import. When some
components are null and the known subtotal differs from total_cost, retain the
source but mark cycles cost_components_unreconciled/PENDING and suppress both
confirmed net returns and account/currency net_booked_pnl. A positive remainder
is also unresolved; settlement agreement alone does not explain its allocation.
Do not infer a missing charge, rebate or zero from the difference. Equal known
subtotal (or no component breakdown) retains the source-total contract; explicit
signed components can resolve rebates. New journal runs recheck stored facts,
while old reports and source evidence remain immutable. Independent-statement
reconciliation checks costs in both supplied rows and stored facts before
certifying coverage. Missing detail never justifies choosing a favorable return. Grouped domestic
orders retain total fees and quantity with shared_order_cost_allocation pending.
A Hyperliquid retained tail may skip an unanchored segment and resume at a later
explicit zero position-before. Skipped fees stay in account totals and the gap
remains visible; no opening inventory is invented.

`data reconcile` provides bounded independent-statement coverage and a supplied
flat opening anchor after exact economic and ending-inventory checks. Completeness
is an explicit operator assertion about an independently obtained source, not a
claim derived from successful API pagination. Changed facts invalidate that
coverage. See docs/unified-data-operations.md for the source format and trust limit.
New journal freshness checks include late historical facts and changed coverage;
old as-of reports/exports remain immutable. Statistics expose excluded_count,
exclusion_reasons and holding_eligible_count in addition to the existing formulas.

Reconciliation also compares provider gross realized PnL; matching fills and fees
alone cannot certify a conflicting closedPnl. Invalidated HL gap segments retain
unknown close time and PENDING quality, but their funding exposure ends at the next
source-backed zero anchor. No later funding is shared with that abandoned segment.

The account-audit workflow captures native inputs separately, compares them without
mutating canonical state, and applies a digest-bound reviewed plan in one local
transaction. It preserves source observations, old revisions and frozen reports;
`--journals` adds fresh selected-account and combined reports atomically. A replay
of the same report does not add duplicate economic facts or journal runs. Audit
comparison is not independent statement certification: coverage remains partial,
unknown inventory/costs remain visible, and the existing metric formulas and pending
return rules continue to apply. See the account audit section of the operations
guide for exact capture, correction authorization and stale-report semantics.

KIS domestic source normalization rejects positive executed orders without daily
and cost corroboration or a recognized `01` sell / `02` buy side. Every executed
order must be represented exactly once by date, symbol, side and order ID in the
normalized facts. Unknown-side zero-executed orders do not create trades. Capture
and audit reuse this validation; re-derived apply rejects before journal writes.
