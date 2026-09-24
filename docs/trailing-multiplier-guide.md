# Daily-volatility trailing multiplier calibration guide

Status: user-accepted initial native/nine-minute TS policy values, not validated
optimal settings, implemented independent distances, or live activation.
Close-only TS supports explicit automatic/manual selection. The accepted manual
status-check starting value is three times the ten-day mean absolute daily close
change, not an automatic execution default.
The [strategy requirements](strategy_execution_design.md#daily-volatility-execution-and-close-briefing-reference-requirements)
own confirmed policy; this guide supplies research context and calibration.
The independent BTC three-hour strategy is outside scope.

## Evidence and transfer limits

Fidelity gives 1.5 times ATR as an example for detecting abnormal movement, not as
an optimized universal trailing-stop setting.[1] Schwab discusses 1.5–2 times ATR
as additional room relative to one ATR and notes the potential position-size
trade-off.[2] StockCharts' Chandelier Exit uses a 22-day high and 3 times ATR(22)
as its default long formula.[3]

These are educational parameter examples, not controlled tests of this
repository's native-mark/nine-minute-bid pair. They support testing a range;
they do not establish an appropriate paired candidate or optimal setting on HL.
No comparable authoritative recommended multiplier was established for the exact
close-to-close absolute-movement metric proposed here. Do not cite ordinary
"close-based ATR trailing stops" as evidence for that metric: anchoring or
triggering at a close does not remove highs/lows from ATR calculation.

Repository fact: `kis_hl.risk.calculate_atr_10d` averages the latest ten daily true
ranges arithmetically. Fidelity's displayed formula uses Wilder smoothing.[1]
The project also freezes management distance, unlike a rolling Chandelier
indicator. Match the actual calculation, snapshot and watermark rules before
transferring published multipliers.

## Fixed comparison contract

For the initial experiment, retain the existing ten-day arithmetic daily ATR:

```text
TR[d] = max(H[d]-L[d], abs(H[d]-C[d-1]), abs(L[d]-C[d-1]))
A = mean(last 10 completed daily TR values available at the decision)
D_9m = k_9m * A
D_native = k_native * A
```

Use the same daily ATR snapshot for both. Do not use nine-minute ATR or rescale
ATR by the square root of a timeframe ratio. Freeze each distance for the initial
comparison; changing the ATR update policy is a separate experiment.

Current local nine-minute trailing ratchets only from valid completed sampled
buckets but checks breaches on fresh prices, not only at the nine-minute close.
Intrabar whipsaws therefore remain possible. A completed bucket can still contain
an upside wick; delaying its inclusion is not the same as removing that wick.

## Accepted initial native/nine-minute policy values

The user accepted the following starting values, with gradual evidence-led
adjustment rather than treating them as permanent or optimal:

- Nine-minute TS: `2 * daily ATR(10D)`.
- Native TS: `3 * the same daily ATR(10D)`.

This subsequent explicit acceptance is separate from the user's earlier
illustration, which remains neither a baseline nor a candidate. These values
are not empirically optimal, an approved live order change, or an implemented
independent-distance configuration. Prior example-anchored proposals remain
withdrawn.

Independent rationale: Schwab discusses 1.5–2 ATR for allowing more movement than
one ATR.[2] StockCharts' established Chandelier reference uses 3 ATR for trailing
trend protection.[3] Use 2 as the relatively responsive local layer and 3 as the
broader continuously tracking native layer. This role assignment is analyst
judgment: neither source tests HL, this pair, arithmetic ATR(10D), frozen distance,
or the repository's price bases. The recommendation is not proven superior to
other settings; a 3-ATR native trail may permit excessive giveback for a short
holding horizon. It does not promise prevention of stop hunting or later native
execution. Native trailing is not a substitute for the entry protective SL.

Keep the same ten-day arithmetic daily ATR snapshot and initially frozen distance
for attribution. Change the recommendation only on measured outcomes and risk
objectives: premature exits versus adverse continuation, net costs, giveback,
tail loss and stability in unseen periods. Do not widen chart-defined entry SL
or increase size to accommodate this TS recommendation. Existing positions and
orders stay unchanged unless separately authorized.

A native/local multiplier ratio is not a universal constant. Under a simplified
same-price-basis, same-activation, no-rounding comparison, let the watermarks be
H_native and H_9m:

```text
T_native = H_native - k_native*A
T_9m = H_9m - k_9m*A
T_native <= T_9m iff
H_native - H_9m <= (k_native-k_9m)*A
```

The multiplier difference supplies watermark headroom in this simplified
comparison, not a numerically established buffer. Actual implementation has
mark-versus-bid differences, activation timing, ratchets and rounding. Measure effective thresholds and which exit fires;
do not claim the native layer is always the outer stop because its multiplier is
larger. Where available, inspect the distribution of positive watermark gaps
normalized by ATR, alongside observed premature exits; it is a diagnostic for the
extra native buffer, not a guarantee or automatic live adjustment rule.

## Daily-close movement TS: automatic or manual selection

The user chooses either automatic execution or manual/briefing-reference mode
for the situation. Persist explicit selection and authority; an unspecified mode
must not authorize automatic exits. Neither mode is activated by this guide.

Accepted initial manual status-check calculation (not an automatic default):

```text
V_close = mean(last 10 abs(C[d]-C[d-1]) values)
manual_reference_distance = 3 * V_close
```

This uses eleven completed daily closes, not highs/lows or a signed mean change.
A highest-daily-close watermark remains a proposal. Fix daily session, finalized
bar evidence and incomplete entry-day treatment. Invalid/zero inputs must not
produce invented distance or substitute high/low ATR silently.

- Automatic: a configured condition at the completed daily close can cause a
  latched authorized exit, with realistic post-confirmation fills, reduce-only
  execution, residual-size reconciliation and native/local race handling.
- Manual: the level/crossing supports contextual briefing analysis and cannot
  produce an exit intent, order or protection change by itself. Chart/strategy
  reasoning may support holding despite a crossing or selling without one.

The user accepted `3 * V_close` for initial manual status checks after the
native/nine-minute policy decision. This is not empirically calibrated and is
not justified by native using the same numeral. Preserve the distinct ten-day
arithmetic close-change estimator rather than silently redefining ATR. Do not
carry this manual observation setting into automatic execution without separately
selecting and validating that mode. Adjust gradually from recorded evidence;
no automatic-mode multiplier grid is selected.

Review the manual setting using warning frequency, subsequent close-price paths,
chart context and missed deterioration. Automatic-mode evaluation, if selected,
needs separate net-performance and tail-risk tests with realistic fills. Ordinary
Chandelier settings are not calibrated multipliers for this close-only metric.

`A / V_close` diagnoses distance scale only. Dynamically multiplying V_close back
into standard ATR defeats the close-only requirement. Neither mode changes the
chart-defined entry SL. Automatic daily confirmation can be preempted by active
native/local intrabar protection; record which layers are active and do not
silently disable or widen them to force a particular exit sequence.

## Executable native/nine-minute selection and validation

1. Lock the entry signals, chart-defined entry SLs, independent exit rules,
   account risk budgets, source/session, ATR snapshot and cost assumptions. Keep
   entry sizing tied to the actual protective loss exposure, not the TS distance.
2. Reconstruct all candidate exit paths from the same entry episodes, including
   rejected or stopped-out opportunities; do not retain only eventual winners.
   Report standalone layers and the combined earliest-exit policy separately.
3. For native/local comparisons, use sufficiently granular mark and bid evidence
   with actual activation/coverage. Trade-candle OHLC is only a proxy and cannot
   determine unknown intrabar ordering. Model feasible fill prices, slippage and
   data delay for executable exits; keep advisory-only reference events separate.
4. Separate trending, ranging and stressed periods. Use chronological training
   and later untouched validation windows; avoid overlapping position leakage.
   Choose broad parameter plateaus, not the highest in-sample PnL point. Test costs
   and gaps adversely. If there are too few independent episodes, label the result
   inconclusive rather than reducing uncertainty to a best-looking multiplier.
5. Compare net PnL, maximum drawdown, tail loss, profit giveback, turnover and cost,
   holding time, emergency-SL hits, native-first/local-first/strategy-exit shares,
   and post-stop recovery over a fixed, predeclared horizon. Recovery alone is not
   evidence an exit was wrong; include adverse continuation after the stop.
6. Hold discretionary chart decisions fixed across candidates for attribution,
   or provide timestamped reproducible strategy rules. A retrospective chart
   interpretation that changes with each result invalidates the comparison.
7. Use paper/shadow observation first. Existing native SL may dominate TS exits;
   report that explicitly. Do not loosen entry SL or disable native protection to
   make a candidate appear effective. Changes to live protection need separate
   authorization and existing safety gates.

This research used external educational sources and inspected local code. It did
not run a market-history backtest, inspect account holdings, establish historical
stop-hunting frequency, start monitoring, or place/modify/cancel any order.

## Sources

[1] https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr
[2] https://www.schwab.com/learn/story/average-true-range-indicator-and-volatility
[3] https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/chandelier-exit
