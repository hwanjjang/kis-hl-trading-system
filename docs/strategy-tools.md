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
python3 -m kis_hl.cli strategy opinion --input review.json [--dry-run]
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

Optional `timing_opinion` holds a `strategy opinion` result for the same
`signal_instrument` and `setup_input.snapshot.id`. Decide rejects a mismatched,
authority-bearing or internally inconsistent opinion: provider, advisory flag,
probabilities, choice, confidence, band and effective opinion are rechecked, and
an unavailable opinion must carry a reason and null opinion fields. Attach the
tool output unchanged: `probabilities`, `confidence` and `min_confidence` must be
decimal strings, so JSON numbers (which parse as rounded floats) are rejected. An `enter`/`add` whose
effective opinion is not `long` (including an unavailable opinion) needs a
non-empty `opinion_note` explaining why the decision proceeds. The opinion never
replaces the predicate, confluence or management checks.

Do not change `signal ingest` legacy integrations automatically; `strategy decide`
is the validated skill interface. Repeated identical decisions are idempotent;
changed inputs require a new decision ID. Existing signal/plan/journal attribution
provides the audit path without a second workflow database.

## Jev timing opinion

`strategy opinion` asks TypeSafe AI's Jev model (a calibrated "System One"
decision model, not a text LLM) one Choice question: is `long`, `short` or `wait`
best supported now? It is an advisory second opinion for the review, never order
authority, sizing input or an execution gate. The strategy is long-only: `short`
means avoid new long exposure or review protection, not open a short.

```json
{
  "instrument": "hl:BTC", "snapshot_id": "source-snapshot-id",
  "asof_ms": 1790006400000, "horizon": "daily swing",
  "facts": {"breakout_predicate": true, "price_vs_30w_ema": "above, EMA rising",
            "atr_10d_pct_of_price": "3.1"},
  "notes": ["Funding neutral"], "min_confidence": "0.5"
}
```

`facts` holds 1–40 flat named values (text ≤ 300 characters, booleans or finite
numbers); `notes` holds at most 10 short strings. Optional `min_confidence` must
be a decimal string in (0, 1]. Supply tool outputs and named
buckets already computed by deterministic tools: Jev is weak at arithmetic, date
comparison and large irrelevant context, so do not ask it to calculate. Only
`instrument`, `horizon`, `facts` and `notes` are sent; `snapshot_id` and `asof_ms`
bind the result locally.

The request is `POST {TYPESAFE_BASE_URL}/v1/systemone` (default
`https://api.typesafe.ai`) with `Authorization: Bearer $TYPESAFE_API_KEY`, a
10-second timeout, no retries and no redirects (a 3xx is unavailable). The base
URL must use HTTPS; plain HTTP is accepted only for loopback test stubs. A key
containing whitespace or control characters is rejected without echoing it. The model defaults to the pinned `jev-1.13.0`
(override with `--model` or `TYPESAFE_MODEL`) so thresholds do not move silently
with the `jev-latest` alias; the output records the model that answered.
`--dry-run` prints the exact request and its `input_sha256` without a key or
network access.

Output always has `tool: timing_opinion`, `provider: typesafe`, `status`, `instrument`, `snapshot_id`,
`asof_ms`, `requested_model`, `input_sha256`, `min_confidence`, `advisory: true`
and `order_authorized: false`. An `available` result adds `model`, raw `choice`,
decimal-string `probabilities` and `confidence`, `band`, `effective_opinion` and
token `usage` (null when the response omits valid counts).
Confidence below `min_confidence` (default 0.5) gives band `low` and effective
opinion `wait`; at least 0.8 is `high`, otherwise `medium`. HTTP errors
(401/422/429/529), transport failures, non-JSON bodies, a different option set,
non-finite or out-of-range probabilities, a sum more than 0.01 from 1, a choice
that is not a highest-probability option (a tie keeps the model's pick among
the tied options), confidence outside [0, 1], an answering model ID over 64
characters or a body over 1 MB produce
`status: unavailable` with a `reason` and null opinion fields; nothing is guessed.
Response numbers are parsed as exact decimals (never floats) and the probability
sum is compared exactly before range, sum and confidence-gate checks; JSON
`NaN`/`Infinity` and values with more than 40 digits or decimal places are
rejected. A missing key is
a configuration error. The key never appears in output.

Jev's answer quality for market timing is unverified in this repository; the
thresholds are conservative starting values. Each call is billed per input token
and subject to TypeSafe's dynamic rate limits. Offline verification:
`python3 scripts/smoke_timing_opinion.py` (local stub, temporary database).

### Repeatability and threshold calibration

Identical inputs can produce different opinions. In two connectivity checks
using the same synthetic input, confidence changed from 0.51 to 0.36, changing
the effective opinion from `long` to `wait` at the default 0.5 threshold.
These two observations establish neither a variability estimate nor trading
accuracy; use real snapshots for the following evaluation before operational
reliance, and repeat it when the model or input construction changes.

1. Freeze a representative set of real market snapshots across instruments,
   setups and market conditions. Preserve the tool-computed facts, notes,
   horizon, source timestamps and snapshot IDs. Fix the requested model version,
   input construction and `min_confidence` for each evaluation batch.
2. Choose the snapshot count and repeat count before calling the API, within an
   explicit cost/rate budget. Call each identical input the same number of times;
   do not refresh facts between repeats or stop when a preferred answer appears.
   Repetition is an offline evaluation procedure, not a retry loop for live entry.
3. Retain every raw tool result, including `unavailable`, with a batch/run ID and
   call timestamp. Record `input_sha256`, requested/returned model, snapshot ID,
   raw choice, all three probabilities, confidence, band, effective opinion and
   threshold. Keep API keys out of records; separate different returned models.
4. Per snapshot, summarize choice/effective-opinion frequencies, probability and
   confidence ranges and quantiles, threshold-crossing frequency, and unavailable
   rate. Report the sample counts. Use code for these calculations; do not ask
   Jev to compute them. Repeated calls measure variability, not independent market
   outcomes or proof that the majority answer is correct.
5. Assess candidate `min_confidence` values against outcomes defined in advance
   for the review horizon, using separate calibration and held-out snapshots.
   Keep all repeats of one snapshot in the same split and prevent future-data
   leakage. Compare directional errors, coverage/abstention and stability;
   record the sample size, model, threshold, rationale and limitations. Do not
   lower the threshold merely to obtain more `long` opinions. Without sufficient
   outcome evidence, retain the provisional default and disclose the limitation.
6. Apply an evidence-supported gate through the decimal-string `min_confidence`
   input. The 0.8 `high` band boundary is fixed in code, not a configurable gate;
   changing it requires a separate code/test/documentation change. Revalidate
   after model/input changes and retain the previous evaluation for comparison.

Before delivering a Hermes review, check that any calibration claim links to
its recorded batch and held-out evaluation. Disclose observed instability and
missing evidence; never select a favorable repeat as the recorded opinion.
Attach the selected tool output unchanged to `strategy decide`, with the
existing `opinion_note` requirement when applicable. Evaluation snapshots are
historical evidence, not fresh authorization to trade.
