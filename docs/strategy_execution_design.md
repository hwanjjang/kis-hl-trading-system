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

The current signal executor accepts entry actions only. Hold/add/reduce/exit and
no-trade records remain advisory; they cannot be accidentally replayed as new
entries. The supervisor rechecks source-evidence freshness and the entry predicate
before entry in addition to its existing execution checks. Legacy `signal ingest`
remains compatible; skills use the validated `strategy decide` interface.

## Confirmed capital and risk policy

Hyperliquid operating capital uses the selected perpetual account value × 10,
without a thousand-USDC floor or a below-1000 exclusion. KIS uses selected account
NAV × 1, valued in the execution currency with an explicit FX basis when needed.
Do not pool main/subaccounts, spot balances or other-dex collateral into the chosen
HL account value. Available funds are a separate constraint. The multiplier does
not set venue leverage or waive margin requirements.

One unit represents planned fixed-stop loss of 1% of operating capital. For example,
2372.90 USDC yields 23729 USDC operating capital and 237.29 USDC planned risk per
unit. The unit calculator accepts the actual proposed entry and fixed SL, rounds
quantity down to the supplied lot step, and reports realized planned risk after
rounding. A below-minimum result cannot be rounded up silently. Costs, slippage
and gaps mean actual losses are not guaranteed to equal planned stop risk.

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

- **Live add-ups:** the current supervisor requires flat entry and owns one active
  position per account/instrument. The skill and tools can evaluate and size an
  add proposal, but cannot submit it by bypassing those guards. Tranche-aware
  execution/protection is a separate execution change.
- **Arbitrary fixed-stop plans:** the tool can calculate against an explicit stop;
  the current managed plan expresses ATR distance and rechecks execution ATR.
  An authorized plan must represent the same risk basis. Do not silently substitute
  another stop to make a proposal executable.
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

## Verification and use

See [CLI contracts and input examples](strategy-tools.md) and
[usage](../README.md#hermes-strategy-tools). Representative tests cover valid and
unavailable setups, strict breakout boundaries, post-entry add-up evidence,
fixed-stop sizing, rounding/minimums, immutable evidence and action/expiry guards.
Reuse the existing supervisor/trailing/journal tests. A focused CLI run with
recorded fixtures and temporary SQLite checks the actual integration; no live
fault injection, exhaustive venue matrix or new notification test suite is needed.
