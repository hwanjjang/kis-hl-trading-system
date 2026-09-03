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

The current CLI accepts one entry price, one exit price, and one quantity. It does not
store individual fills. For a completed position with partial fills, the caller must
provide quantity-weighted average prices:

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
