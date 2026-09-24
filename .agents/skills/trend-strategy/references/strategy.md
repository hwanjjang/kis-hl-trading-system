# Long trend strategy, version 1

## Universe and evidence

Use the existing eligible instrument universe and account-specific execution
policy in [operations](../../../../docs/trading-operations.md). No asset or live
permission is added by this skill. Prefer KIS reference data where the configured
route is usable; use explicitly identified matching Hyperliquid data where it is
not. A shared market-timing decision does not convert index points into ETF/perp
prices, ATR or stop distances. Review configured funding/spread requirements with
the source evidence; do not invent universal thresholds.

For the general strategy, the latest complete weekly close must exceed the
30-week EMA. Review daily/4H trend structure and more than one supporting factor,
such as prior resistance, moving-average alignment or a documented retest.
Confirm the chosen setup with a closed candle. Avoid unexplained reference levels
and unsupported scores. The code's rules below are a concrete first definition;
change their meaning only with a new strategy version and relevant tests.

## Setups

| Setup | Numeric predicate in `strategy evaluate` | Skill judgment |
| --- | --- | --- |
| Breakout | Latest closed candle close strictly exceeds the highest high of the chosen prior lookback window; weekly filter passes. Default lookback is one. | Choose the timeframe/window and explain why the prior high represents meaningful resistance with supporting context. |
| Pullback add | The previous closed post-entry candle intersects the explicit reference ± tolerance band; the next closed candle closes above that reference, the previous high and its own open. Weekly filter passes and the close is above the position's effective stop. | Select a supported moving-average/breakout/ATR reference and tolerance; verify the actual owned position and explain the rebound. |
| Rebreakout add | Latest closed candle closes above the configured lookback high using only complete post-entry candles; weekly filter passes and close is above the effective stop. | Establish that the window represents the post-entry swing/consolidation rather than arbitrarily shortening it. |
| Management | A fresh matching-instrument price at or below the supplied effective stop returns `stop_crossed`. | Reconcile actual coverage and exposure, and recommend hold/reduce/exit based on the stored plan and changed context. Do not wait for this review to provide continuous protection. |

Add-ups require an identified, fresh, positive long position in the execution
instrument and at least two complete post-entry bars. They are not averaging
below the current stop. Each proposed tranche uses its own entry and fixed stop
for sizing; evaluate its effect on the existing position and management plan.
There is no strategy-wide per-asset/portfolio stop-risk cap or add-count limit.
Actual available funds, notional bounds and granted authority still constrain
execution. The current managed executor does not yet accept live add-ups.

## Capital, stop and size

The capital and unit tools implement the confirmed policy: Hyperliquid selected
perpetual account value × 10 without flooring; KIS selected account NAV × 1 in the
execution currency. Do not pool accounts, count collateral twice or confuse NAV
with buying power. One unit is a planned fixed-SL loss of 1% of operating capital.
It can represent about 10% of unmultiplied HL account equity; disclose both figures.
The multiple does not command exchange leverage or waive margin checks.

Use `strategy stop` for ATR(10D) and the asset-class N defaults owned by
`kis_hl.risk`, or explain an explicit structural SL. Use `strategy size` for the
selected number of units, actual lot/minimum rules and final fixed stop. There
is no invented default maximum-unit recommendation. Recommend only a count
supported by observed funds and the user's bounds. Missing evidence stays missing.
Trailing-risk improvement can inform a new proposal; it neither resizes an
existing approval nor replaces the fixed SL used to size a new tranche.

## Protection and exits

After actual fills, existing management confirms fixed protection and starts the
selected supported trailing policy at its earliest verified point, without a
profit/breakeven prerequisite. Loss exits are allowed. Keep fixed SL while TS is
being established and afterward under existing operations policy.

Reuse the existing `Trail` calculation/worker for the local frozen-ATR policy:
only valid closed post-entry nine-minute bars advance the high/threshold, the
threshold never decreases, and fresh matching prices check crossings. Native HL
trailing follows a different continuous mark-price policy. Do not silently swap
providers, mix source watermarks, infer active coverage from acknowledgements, or
claim percentage TS support from the quote-distance managed interface.

The [daily-volatility policy](../../../../docs/strategy_execution_design.md#daily-volatility-execution-and-close-briefing-reference-requirements)
owns the accepted initial local/native daily-ATR multipliers and close-only
manual/automatic modes. Independent local/native distances are supported; use
the operations contract rather than silently migrating existing orders. Close TS
defaults to manual briefing reference unless explicitly requested otherwise.
A manual crossing never grants exit authority.
Entry SL and chart-based exits remain independent of trailing references.

Hold when the thesis and observed protection remain valid. Consider reduction or
exit when context invalidates the setup, funding/spread suitability changes or
the user's exposure instructions require it; state the evidence and judgment.
Protective exits remain local to the account and never depend on Hermes uptime or
a peer venue. Use actual fills and the existing journal for completed-trade review.

## BTC exception

This is an independent, opt-in strategy under the [activation policy](../../../../docs/trading-operations.md#btc-three-hour-strategy-activation-policy).
Evaluate it only when explicitly requested; a general BTC review or briefing does
not activate it. A review does not start a persistent monitor, and observation
never grants live trading authority. Do not infer position attribution from BTC
holdings alone.

The existing BTC rule observes Hyperliquid UBTC/USDC spot, using complete 3H
candles. The latest close must strictly exceed the previous high (or explicitly
selected lookback high). `setup: btc_3h` invokes the existing predicate and does
not add the general weekly filter to this exception. It still requires rationale,
confluence notes and a management plan before a skill entry proposal.

Execution is the BTC perpetual, not spot. Use perpetual ATR(10D) × 2 for the stop
candidate and `sizing: btc_fixed_80` for a fixed 80-USDC notional rounded down.
Do not migrate this exception to unit sizing or use spot ATR for perp protection.
Persist the explicit spot source in decision evidence while the registered signal
and execution catalog IDs are `hl:BTC`. Use existing protected execution, not the
legacy monitor's immediate entry-and-stop submission.
