---
name: trend-strategy
description: Review long trend-following breakout, pullback and rebreakout setups for Hermes using deterministic repository tools. Produce explained enter/add/hold/reduce/exit/no-trade decisions and explicit risk-unit proposals; includes the BTC spot-3H/perp exception. Use for strategy reviews, not as permission to trade.
---

# Trend strategy

Read [the strategy rules](references/strategy.md) for selection and management.
Use [the tool contract](../../../docs/strategy-tools.md) when preparing inputs.
The shared [authoring policy](../../../docs/strategy-authoring.md) owns the
skill/code boundary. Hermes owns review timing, conversation, briefing and delivery;
this skill adds no scheduler or notification transport.

## Review

Identify the account, actual holdings and pending/protective orders, the analysis
instrument and each execution instrument. Obtain fresh source evidence through
existing data/account tools. Missing account data is not an empty portfolio.
Use complete source bars and preserve their identity; a chart page alone does not
establish coverage. Work per account and currency.

Call `strategy indicators` and `strategy evaluate` for the numerical facts. Choose
and explain the setup's reference level, timeframe and confluence. The tool's
`predicate_passed` is one input to the decision, not a recommendation or order
permission. Record two distinct supporting reasons for an entry or add, but do
not pad the rationale to pass a validator. If the setup or necessary evidence is
missing, return a reasoned `no_trade` (or `hold` only when the known position and
protection support it). Do not turn an unavailable result into false/zero.

Call `strategy stop` with execution-instrument ATR to derive an initial candidate
SL, or use a justified explicit structural stop. Call `strategy size` with that
fixed stop and the user's proposed unit count. Use the returned quantity, risk,
notional and equity/capital percentages in the proposal; do not recompute them in
text. Explain costs and fill uncertainty without claiming a guaranteed loss cap.
A below-minimum result means skip/review, never silently round up. Use the BTC
fixed-notional option only for the documented exception.

Register the skill strategy/version and explicit instrument set with
`strategy register`, then use `strategy decide` to retain the actual setup input,
numeric evidence, rationale, management plan and timestamps in the existing
signal registry. Keep relevant size/source output alongside the decision.
Use a new decision ID after changing inputs. Repeated identical records are safe.
Record hold/reduce/exit/no-trade outcomes as well as successful setups; do not
invent deterministic reasons for discretionary reduction or exit decisions.

## Execution handoff

Follow [protected operations](../../../docs/trading-operations.md) with an explicit
execution plan and actual manual authority or a bounded grant. Decision ingestion
alone authorizes nothing. Preserve the approved fixed-stop risk basis; if the
current ATR-distance plan cannot represent it, report that limitation instead of
substituting a different stop. Existing order preparation and preflight remain
responsible for prices, funds, lots, sessions, metadata and protection.

Only entry decisions use the current `signal execute` path. An `add` decision is
a strategy proposal: the current supervisor requires flat entry, so do not route
it as a second entry or bypass ownership through raw orders. Likewise, use explicit
existing position controls for an authorized exit; a signal is not a liquidation
instruction. The legacy BTC monitor is not the protected execution path for this
skill. Percentage TS, partial reductions and live add-ups require their own
supported execution contract; surface unavailable capabilities plainly.

Review closed trades through the existing journal and its `trade-journal` skill.
Use stored strategy/signal evidence for attribution. No notification delivery
result or unexecuted proposal belongs in realized performance.
