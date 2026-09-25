# Strategy tools

These tools read explicit JSON snapshots supplied by Hermes or another caller.
They do not collect market/account data, schedule reviews, send notifications or
place orders. Use existing data/account commands for collection and preserve their
source and completeness metadata. `complete: true` is a caller assertion of a
closed, covered bar, not something to manufacture from a recent receipt time.

```bash
python3 -m kis_hl.cli strategy indicators --input snapshot.json
python3 -m kis_hl.cli strategy evaluate --input setup.json
python3 -m kis_hl.cli strategy stop --input stop.json
python3 -m kis_hl.cli strategy size --input size.json
python3 -m kis_hl.cli --db data/trading.sqlite strategy decide --input decision.json
```

Read-only tools accept `--as-of-ms` for offline replay. Decision persistence uses
the actual clock. Register an immutable strategy version through `strategy register`
before recording decisions. `signal list` displays the resulting records.

## Snapshot and setup inputs

A snapshot contains `id`, `instrument`, `source`, `currency`, `asof_ms` and
`max_age_ms`. Timestamps are UTC epoch milliseconds. Use explicit catalog IDs, such
as `index:KOSPI`, `kis:122630` and `hl:BTC`. The BTC spot predicate additionally
accepts `hl:UBTC/USDC` as an analysis-only source identity; it does not add a live
execution instrument to the catalog.

Each bar has `start_ms`, `end_ms`, `open`, `high`, `low`, `close`, and `complete`.
Prices are decimal strings. All bars must be ordered, non-overlapping and closed
at the supplied clock. `candles` must have the snapshot's `timeframe_ms` duration
and no gaps. `daily_bars` use complete UTC 24-hour buckets; `weekly_bars` use
complete contiguous UTC seven-day buckets. The weekly input must already have
calendar/session completeness established by the data source or collector.
This initial adapter does not silently reinterpret exchange-local/DST bars:
normalize with evidenced calendar semantics first or report them unavailable.
Partial weeks are rejected, not included in the EMA.

The shared BTC breakout helper also accepts `start_ms` and `end_ms`, preserving
them in its current/reference candle timestamps. Existing helper aliases such as
`t`/`T` keep precedence when both forms are supplied. Strategy snapshots still
require ordered canonical bars; helper normalization does not relax validation.

`history_max_age_ms` supplies explicit `daily` and `weekly` freshness budgets.
The indicator tool requires 11 daily bars for ATR(10) and 30 weekly bars for EMA;
it reports missing indicators independently under `unavailable` with null values.
The setup tool rejects missing required history rather than substituting it.

```json
{
  "setup": "breakout",
  "lookback": 1,
  "snapshot": {
    "id": "source-snapshot-id",
    "instrument": "hl:BTC",
    "source": "Hyperliquid",
    "currency": "USDC",
    "asof_ms": 1790006400000,
    "max_age_ms": 60000,
    "timeframe_ms": 10800000,
    "history_max_age_ms": {"daily": 345600000, "weekly": 864000000},
    "candles": [],
    "daily_bars": [],
    "weekly_bars": []
  }
}
```

Empty arrays above intentionally produce unavailable evidence. Supply real closed
bars before use. Sample freshness budgets are explicit fixture values, not global
trading defaults; choose them for the instrument and session.

Setups: `breakout`, `pullback`, `rebreakout`, `btc_3h`, `management`.
Pullback also needs `reference` and non-negative `tolerance` in the snapshot's
price units. Add-ups require `position`: `id`, `scope`, matching `instrument`,
positive `quantity`, effective `stop`, `opened_ms`, `asof_ms`, `max_age_ms`.
At least two complete post-entry candles are required. For cross-venue analysis,
evaluate market context separately and use the execution instrument's own prices
for comparisons against its stop; never compare index points to an ETF stop.
Management uses a fresh snapshot `price` and matching position instead of bars.

Results contain `status`, `predicate_passed`, numeric `facts`, `reasons`, source
identity, snapshot ID and an input SHA-256. `order_authorized` is always false.
Passing the predicate does not establish confluence, suitability, session
eligibility, funds or protective coverage.

## Stop and size inputs

`strategy stop` accepts `entry`, `atr`, and either explicit `multiple` or
`asset_class`. Defaults come from `risk.n_multiplier_for_asset_class`.
Optional `side` is `long` by default. The output is a proposed stop/distance,
not a market-rounded protective order or confirmed stop. Use ATR in the execution
instrument's units; stop rounding belongs to the existing execution path.

```json
{"entry":"100","atr":"2","asset_class":"stock"}
```

`strategy size` uses the final proposed fixed SL, never a tighter trailing threshold:

```json
{
  "venue":"hyperliquid", "scope":"mainnet:account-id", "currency":"USDC",
  "instrument":"hl:BTC", "asof_ms":1790006400000,
  "capital_evidence": {
    "scope":"mainnet:account-id", "currency":"USDC",
    "asof_ms":1790006400000, "max_age_ms":60000, "account_mode":"unifiedAccount",
    "spot":{"balances":[{"coin":"USDC", "token":0, "total":"999"}]}
  },
  "max_age_ms":60000, "entry":"100", "stop":"97", "units":"1",
  "quantity_step":"1", "minimum_quantity":"1", "minimum_notional":"10"
}
```

The example's market rules are fixtures; read actual lot/minimum metadata.
HL equity is the selected account's reconciled total balance; follow the
[account-mode and collateral-overlap contract](trading-operations.md#user-approved-risk-units).
The sizing tool validates supplied source evidence; it does not fetch live totals. `capital_evidence`
is mandatory; caller `equity` is not a fallback. Supported unified USDC balances
count overlapping spot/perp/DEX collateral once. Unknown modes, duplicate collateral,
unvalued assets, stale evidence or wrong account/currency block sizing. Reconciliation
also rejects nonzero/malformed escrow, borrowed or supplied components and
contradictory portfolio-margin state. Obtain
source evidence through `account capital --venue hyperliquid`. KIS equity is the selected account NAV valued in the
execution currency, with an explicit FX basis when needed. Buying power is a
separate preflight constraint. Output includes rounded quantity, notional, planned
risk, capital, and risk percentages against capital and equity. `below_minimum`
means do not submit; never round up. Arithmetic accepts short stops, but the
strategy and managed execution remain long-only.

For the documented BTC exception, set `sizing: "btc_fixed_80"`, omit `units`, and
use `instrument: "hl:BTC"`. The tool rounds the quantity for an 80-USDC notional
down and reports actual fixed-stop risk. It never silently changes that strategy
to one-unit sizing.

## Decision records

Use the existing signal fields: `id`, `strategy`, `strategy_version`,
`signal_instrument`, `execution_instruments`, `observed_ms`, `expires_ms`,
`rationale`; add `action`, `setup_input` (the complete setup request),
`confluence` and `management`. The tool recomputes evidence before persistence
and the existing registry makes the record immutable. Entry/add decisions need
a passing matching predicate, at least two distinct supporting notes and a
management rationale. Notes are reviewable assertions, not independently verified
market facts. Optional size-tool outputs and other evidence can be retained as
additional record fields; they are not execution permission.

Actions are `enter`, `add`, `hold`, `reduce`, `exit`, `no_trade`. `enter` uses
the new-entry path. `add` uses the bounded existing-owner contract in
[operations](trading-operations.md#bounded-conditional-add-ups), with a separate
explicit plan and manual/grant authority. For `enter`, supplied `setup_input` must describe `breakout` or
`btc_3h`; evidence is rechecked before entry, including for raw `signal ingest`
records. Legacy records without `setup_input` remain compatible. Hold/reduce/exit/no-trade records remain advisory: authorized exits use existing
explicit full-position controls. A completed-bar add proposal alone cannot trade.
Add preview requires a registered `signal_id` and reports the earliest evidence/
signal expiry in `sizing.max_expires_ms`. Approval rejects a longer requested expiry;
the preview does not alter the plan or grant authority. Grant expiry remains an
additional bound. Temporary account entry/protection work may delay an unsent add
within these deadlines; source freshness remains mandatory at submission.
BTC spot decisions use `signal_instrument: hl:BTC`, only `hl:BTC` execution, and
retain the explicit spot basis in `setup_input`/evidence.

Do not change `signal ingest` legacy integrations automatically; `strategy decide`
is the validated skill interface. Repeated identical decisions are idempotent;
changed inputs require a new decision ID. Existing signal/plan/journal attribution
provides the audit path without a second workflow database.
