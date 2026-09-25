# Strategy integration design

This document describes the completed strategy-skill/tool contract and its boundary
with existing execution. Strategy selection rules live in the canonical
[trend-strategy skill](../.agents/skills/trend-strategy/SKILL.md), not in a second
strategy daemon. The [authoring policy](strategy-authoring.md) defines which work
belongs in skills versus deterministic code. Hermes owns review timing, agent
invocation, conversation, briefings and notification delivery.

## Current responsibilities

| Component | Implemented responsibility |
| --- | --- |
| `trend-strategy` skill | Long breakout, pullback/rebreakout review, confluence, risk-unit proposals, management reasoning and the BTC exception |
| `kis_hl.strategy_tools` | Closed/fresh input validation, ATR/30W EMA evidence, numeric setup predicates, ATR stop proposal, explicit-stop sizing and validated decision ingestion |
| `kis_hl.risk` | Decimal capital, ATR, EMA, asset-class N and risk-unit calculations |
| `kis_hl.strategy_signals` | Immutable strategy versions/decisions, expiry, bounded grants and explicit entry authority; rechecks skill evidence before entry |
| `kis_hl.managed_execution` / gateways | Existing protected entry, fill reconciliation, account ownership, native/local protection, restart recovery and exit cleanup |
| `kis_hl.trailing` / worker | Existing local frozen-ATR trailing calculation and supervised management; native provider integration remains explicit |
| Existing journal ledger | Actual-fill synchronization, strategy attribution and completed-trade review |
| Hermes | Contextual strategy decisions, review cadence, user-selected units and briefing/notification workflow |

This replaces the original proposal to build a strategy-evaluation daemon and a
new set of parallel strategy/position tables. Reuse the existing registry, managed
positions/attempts and journal ledger. Strategy skill/tool completion does not
assert that every historical live-execution proposal is implemented.

## Decision and execution flow

```mermaid
flowchart LR
  Data["Explicit market/account evidence"] --> Tools["Deterministic CLI tools"]
  Hermes["Hermes + trend-strategy skill"] --> Tools
  Tools --> Hermes
  Hermes --> Decision["strategy decide: immutable evidence + rationale"]
  Decision --> Approval["Explicit manual authority or bounded grant"]
  Approval --> Plan["Existing execution plan + preflight"]
  Plan --> Managed["Fill-aware supervisor and protection"]
  Managed --> Journal["Actual-fill journal"]
```

The skill chooses and explains context; code tests precise predicates and performs
arithmetic. `predicate_passed` alone is not a signal, permission, risk approval or
proof of protective coverage. Setup, stop and sizing outputs carry
`order_authorized: false`. Invalid/stale inputs produce unavailable evidence;
missing facts must not become empty positions or zero risk.

`strategy decide` accepts the existing registered strategy/version and signal
identity fields plus action, original setup inputs, confluence and management
rationale. It recomputes evidence and persists it in the existing immutable signal
record, including source/snapshot identity and an input digest. An identical
replay is idempotent; changed inputs need a new decision ID. Existing signal/plan
identifiers provide journal attribution without inventing realized trades.

The signal executor accepts entry and bounded existing-owner add actions.
Hold/reduce/exit/no-trade records remain advisory. Add requires its own explicit
plan and authority; it cannot be replayed as a new entry. The supervisor rechecks source-evidence freshness and the entry predicate
before entry in addition to its existing execution checks. Legacy `signal ingest`
remains compatible; skills use the validated `strategy decide` interface.

## Confirmed capital and risk policy

### Capital model

Hyperliquid operating capital uses the selected account's reconciled total balance × 10,
without a thousand-USDC floor or a below-1000 exclusion. KIS uses selected account
NAV × 1, valued in the execution currency with an explicit FX basis when needed.
Keep main/subaccounts separate and count overlapping spot/perp/DEX collateral
only once. Missing or ambiguous total reconciliation blocks automatic sizing.
This supersedes the individual perp/DEX accountValue basis; the source contract
is owned by [operations](trading-operations.md#user-approved-risk-units).
The initial implementation supports verified unified USDC-only balances; nonzero
or malformed escrow, borrowed/supplied components and contradictory portfolio
mode evidence are rejected. Other modes/valuations require explicit supported
reconciliation. Available funds are a separate constraint. The multiplier does
not set venue leverage or waive margin requirements.

### Position sizing

One unit represents planned fixed-stop loss of 1% of operating capital. For example,
2372.90 USDC yields 23729 USDC operating capital and 237.29 USDC planned risk per
unit. The unit calculator accepts the actual proposed entry and fixed SL, rounds
quantity down to the supplied lot step, and reports realized planned risk after
rounding. A below-minimum result cannot be rounded up silently. Costs, slippage
and gaps mean actual losses are not guaranteed to equal planned stop risk.

### Portfolio risk caps

The confirmed policy removes the former 2% per-asset / 6% total stop-risk caps and
two-add-up count limit. Existing funds, order-notional, correlated exposure,
max-loss and authorization bounds remain in force; this is not permission to
remove executable safety checks. No maximum unit count is invented by the skill.
A better trailing threshold may inform another proposal but cannot silently
increase an approved quantity or replace the fixed SL used to size a new tranche.

`strategy stop` reuses execution-instrument ATR(10D) and asset-class N defaults.
The sizing tool accepts a final explicit stop, including a justified structural
stop. Short-side arithmetic is available to the calculator; this skill and managed
execution remain long-only. The BTC exception keeps fixed 80-USDC entry notional
and perpetual ATR × 2 instead of silently migrating to unit sizing.

## Data and price basis

The [tool contract](strategy-tools.md) defines explicit snapshot/bar schemas.
The initial adapter uses complete UTC daily and weekly buckets, rejects partial
weeks and gaps in weekly/confirmation history, and makes history depth/freshness
requirements observable. Existing collectors/data tools remain responsible for
source coverage and calendar normalization. No new data daemon is installed.

The strategy prefers a usable configured KIS reference route; explicit HL fallback
is allowed when its basis is appropriate. Never blend providers inside a candle
or carry a watermark across price bases. Analysis indices, leveraged ETFs and
perpetuals are distinct instruments. Entry/stop sizing uses execution-instrument
prices and ATR, even when market timing comes from another series. Cross-venue
comparison/fallback rules remain owned by [operations](trading-operations.md#cross-venue-timing-and-preferred-execution-policy).

### Breakout entry

The BTC three-hour strategy is independent and opt-in under the
[activation policy](trading-operations.md#btc-three-hour-strategy-activation-policy).
A general BTC review does not activate it; review, monitoring and trading authority
remain separate.

For BTC, spot 3H candles supply only the timing predicate; perpetual data supplies
execution price, ATR, quantity and protection. The shared skill uses the existing
closed-candle BTC predicate through the deterministic wrapper.

## Existing protection and execution limits

Use the protected operations path for authorized orders. It persists attempts
before network I/O, reconciles actual fills and unknown outcomes, retains account
ownership and handles restart/cleanup. Order acknowledgement is not verified
coverage. Missing or inconsistent protection follows the existing intervention
policy, not a strategy-specific raw-order workaround.

Local trailing uses the existing `Trail`: frozen ATR distance, closed valid
post-entry nine-minute bars for high/threshold updates, fresh ticks for crossing,
monotonic thresholds and preserved state on restart. Native trailing uses a
different continuous mark-price contract. Preserve the chosen provider and fixed
SL during trailing activation; do not claim one provider is equivalent to another.
Immediate activation means the earliest supported verified point after fill and
protection, with no profit/breakeven prerequisite. Detailed lifecycle and recovery
behavior remain in [protected operations](trading-operations.md).

The following execution capabilities are separate from completing the strategy
skill and its deterministic tools:

The [exit quantity policy](trading-operations.md#exit-quantity-policy) distinguishes
full strategy/SL/TS exits from discretionary top-based half-position proposals.
It applies to aggregate exposure after adds. Half-position execution remains
outside this implementation and is deferred to #28.

- **Bounded add-ups:** implemented by issue #27 under the existing account/instrument
  owner, with immutable tranche evidence, one durable signal lifecycle, total-account
  sizing and full-remaining-position SL/TS. See the
  [operating contract](trading-operations.md#bounded-conditional-add-ups).
- **Fixed-stop risk preservation:** explicit `fixed_stop_price` is supported
  independently of ATR-based trailing distances. Plan validation checks the entry-to-
  stop distance against approved loss/notional limits. Preserve the sizing stop
  rather than silently substituting an ATR-derived stop.
- **Managed percentage TS and partial reductions:** available low-level fields or
  advisory decisions do not establish an end-to-end managed contract. Use only
  supported existing controls and expose unavailable capabilities.
- **Legacy BTC monitor:** its direct entry/requested-size stop path is not the
  skill's protected execution path. Its in-process deduplication and signal-price
  protection remain legacy limitations; use persisted skill decisions and the
  managed path for this workflow.
- **Cross-venue automatic routing:** Hermes can review explicit pairs and prepare
  independent proposals. Broker eligibility/fallback and asynchronous venue
  outcomes cannot be inferred from shared timing; current plans use explicit IDs.

These limits are reported, not hidden behind successful strategy-tool tests. No
live order, outage or cancellation behavior was verified by this change.

## Daily-volatility execution and close-briefing reference requirements

These requirements do not change active plans, live orders or implementation
defaults. Current execution behavior is owned by
[trading operations](trading-operations.md). Research and calibration limits are
in the [multiplier guide](trailing-multiplier-guide.md).

#### Executable TS: shared daily ATR, separate multipliers

Native and nine-minute TS use the same completed-daily-bar ATR calculation with
separate multipliers. Nine minutes describes the local trailing cadence, not
the volatility timeframe. User numerical examples are illustrations only, not
selected values, baselines, candidate grids or calibration priors. In a subsequent
explicit decision, the user accepted starting at nine-minute `2 * ATR(10D)` and
native `3 * the same ATR(10D)`, then adjusting gradually from observed results.
These are approved initial policy values, not empirically optimal parameters.
The separately scoped BTC retrospective rule is unchanged. Independent distances
are implemented; this policy record alone does not authorize live activation.
Existing positions and orders are not silently migrated.

Native and nine-minute TS are executable protection: an active authorized
trigger begins closing without waiting for daily briefing analysis. Triggering
does not guarantee immediate or complete fills. Current local `Trail.tick`
ratchets from complete nine-minute sampled buckets and checks each fresh price
for breaches. Managed HL uses best bid, legacy trailing uses allMids, and native
trailing follows continuous mark price. Compare effective thresholds rather
than multiplier ordering alone, because watermarks and price bases differ.
Managed plans support independent `local_atr_multiple` and
`native_atr_multiple` over the same frozen ATR; each falls back to legacy
`atr_multiple` when omitted. `fixed_stop_price` preserves an explicit SL independently.
See [operations](trading-operations.md) for validation and activation requirements.

#### Close-based TS: explicitly selected automatic or manual mode

Close-based TS defaults to manual/briefing-reference mode unless the user
explicitly requests automatic execution. An omitted mode is manual, not unresolved
permission to trade. Use the reference in close briefings without creating exit
intents or changing protective orders. Automatic mode requires explicit selection,
validated parameters and execution authority. Do not switch an active position's
explicit mode silently; persist the selected mode with its authority.

Both modes use volatility calculated from completed daily closes alone, not
highs/lows. For initial manual status checks, the accepted starting calculation
is `V_close = mean(last 10 abs(C_t - C_(t-1)) values)` with a reference distance
of `3 * V_close`, requiring eleven completed daily closes. Give this a distinct
metric identifier instead of redefining standard ATR. This is an observation
starting point, not an empirically calibrated loss boundary; review and adjust
from recorded outcomes. Watermark initialization and update semantics still need
specification before an executable implementation. Do not inherit the manual
multiplier into automatic mode without explicitly selecting and validating that
mode's parameters and authority.

- Automatic: after a valid finalized daily close meets the explicitly configured
  TS condition, an authorized management path persists a reconciled exit intent
  and executes under existing safety rules. Do not trigger from an unfinished
  daily candle or assume a fill at the recorded close. Confirmed exits remain
  latched and reconcile partial fills and competing native/local exits.
- Manual/briefing: report the level, crossing, timestamp, data quality and chart/
  strategy context. A crossing is evidence, not a mandatory sell, and creates no
  exit intent, executable order, or protection change. A subsequent trade needs
  a separate applicable decision and authorization.

Chart analysis or another selected strategy may support selling before TS in
either mode; TS is not an AND gate for all exits. A briefing recommendation is
not itself an order. Native/local protection remains independent and must not be
delayed, widened or disabled merely to wait for the daily-close policy. Confirm
concurrent protection explicitly: an intrabar stop can preempt daily confirmation.

Pin instrument, price basis, daily session/timezone, finalization and entry-day
coverage. Missing inputs yield an explicit unavailable/degraded state, never an
invented crossing; retain verified protection. Do not substitute the next
session's opening quote for the previous daily close.

#### Entry SL and strategy decisions remain independent

At entry, choose SL from chart structure and relevant strategy evidence. A
pullback setup can use an invalidation price rather than an ATR multiple. Support
an explicit stop price and rationale; volatility-derived SL is an option, not
a universal requirement. Briefing references neither define nor replace the
actual protective entry SL.

Size using approved entry-to-protective-stop loss exposure, costs and account
risk limits, not the briefing reference or a tighter TS distance. Do not widen
existing stops or increase size without authorization. Keep chart/strategy sells,
executable TS triggers and analytical reference crossings distinct in records.
A strategy sell need not wait for TS; a briefing recommendation is not an order.

#### Verification and research requirements

For executable TS, test shared daily ATR with independent multipliers, ratchet
and breach semantics, gaps, restart idempotency, partial fills, native/local
races and reduce-only cleanup. Compare net returns, costs, drawdowns, tail loss
and giveback under fixed entry/SL/strategy rules. Daily OHLC cannot establish
native intrabar trigger ordering.

For both close modes, test invariance to high/low-only changes, finalized daily
inputs, explicit missing-data output and explicit mode selection. Manual mode
must create no exit intent/order/protection change on a crossing; evaluate its
briefing usefulness and warning quality. Automatic mode requires authorized,
idempotent exit handling, partial-fill reconciliation and native/local race
coverage; evaluate net returns and tail risks with realistic post-close fills.
A mode change must not retrospectively execute an old manual-mode observation
without a newly authorized, reconciled decision.

These requirements are documented, not implemented or empirically validated.
This clarification starts no orders, monitors or scheduled jobs.

## Verification and use

See [CLI contracts and input examples](strategy-tools.md) and
[usage](../README.md#hermes-strategy-tools). Representative tests cover valid and
unavailable setups, strict breakout boundaries, post-entry add-up evidence,
fixed-stop sizing, rounding/minimums, immutable evidence and action/expiry guards.
Reuse the existing supervisor/trailing/journal tests. A focused CLI run with
recorded fixtures and temporary SQLite checks the actual integration; no live
fault injection, exhaustive venue matrix or new notification test suite is needed.
