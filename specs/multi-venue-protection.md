# Multi-venue protected trading specification

Status: proposed design, 2026-09-12. Not implemented by this planning task.
Intent: [multi-venue-protection](../intent/multi-venue-protection.md).
Operational verification and remaining venue limitations: [trading operations](../docs/trading-operations.md).

## 1. Identity and analysis contract (MV1)

Every trade plan resolves separate `signal_instrument_id` and
`execution_instrument_id`. Execution identity includes broker/exchange, account,
environment, asset class, listing venue, symbol, currency and contract identifier.
A label, chart alias or matching ticker is never an execution identifier.

| Strategy family | Analysis sources | Execution candidates |
| --- | --- | --- |
| Korean index | KOSPI (U/0001); KOSPI200 is a separately named optional input | KIS 069500 / 122630 |
| US broad index | S&P500 (SPX); optional explicit SPY proxy | KIS SPY / UPRO; verified HL S&P-style perpetual |
| US technology index | Nasdaq-100 (NDX, verify master); optional explicit QQQ proxy | KIS QQQ / TQQQ; verified HL Nasdaq-100-style perpetual |
| Crypto | Matching HL BTC / ETH candles | Matching BTC / ETH perpetuals |
| Gold | GLD and/or selected gold reference, named in the plan | KIS GLD or verified HL GOLD perpetual |
| Quantum | QPUX or explicitly specified independent analysis basket | KIS QPUX; no HL substitute assumed |
| Memory | DRAM ETF or separately specified memory reference | KIS DRAM ETF or separately verified HL DRAM contract |

KOSPI and KOSPI200 are different. Verify QPUX and DRAM issuer identities and
KIS acceptance or HL underlying mappings against current source evidence before use.
An ETF and a similarly named perpetual are separate assets, not interchangeable
holdings. Each execution chooses one venue explicitly; no automatic cross-venue
hedging, capital transfer or failover trade is part of this design.

Charts retain source, timestamp, exchange timezone, session, interval, currency,
adjustment/split policy and complete-bar status. Index-to-ETF substitution must
be visible in preview; never splice proxy bars into an index history silently.
Use sufficiently fresh execution-instrument quotes for sizing and protection.
Leveraged ETF returns are daily objectives, not a constant price conversion.

Protective thresholds use actual execution-instrument fill prices and volatility.
An index signal may authorize entry or request exit, but its numerical level is
never submitted as an ETF/perpetual stop price. ATR(10D), multiplier, trailing
cadence and price basis are versioned per strategy. Existing HL trailing semantics
remain unchanged until a separately tested migration. Missing history blocks a
strategy requiring it, including a 30-week indicator on a recently launched ETF.

## 2. Capability registry and provider selection (MV2)

Capabilities are keyed by venue, environment, account class, instrument/asset class,
listing exchange, side, session, effective date and API revision. Each row records:

- `capability`: limit, market, stop-market, stop-limit, native-trailing, grouped
  entry, cancel, amend, order query, fills, tradable quantity and price feed.
- `status`: unknown / documented / verified / unsupported; evidence URL/revision,
  checked time, effective-from/to, verification method and limitations.
- Exact order enum, required fields, side-specific trigger comparator, price source,
  equality/crossing/gap handling, post-trigger type, expiry, session carryover,
  partial-fill behavior, quantity reservation, cancellation and amendment semantics.

`Documented` never automatically means `verified`. Native protection is selectable
only when every required dimension satisfies the plan. Expired/unknown evidence
cannot become native support by default. A stop-limit capability is evaluated
against the policy's execution requirements: it can remain unfilled after a gap.
If the configured policy requires market-style liquidation, stop-limit alone
cannot satisfy it. Do not silently change order type to pass preflight.

| Venue/product | Native fixed SL | Native trailing | Initial design choice |
| --- | --- | --- | --- |
| HL eligible perpetual | Trigger SL API documented; live coverage still requires readback | Not verified in reviewed API | Native fixed SL plus existing local trailing after its enrollment preconditions hold |
| KIS domestic 069500/122630 | Unknown for protective SELL semantics and exact ETF/API/session eligibility | Unknown | Supervised local SL and trailing unless exact native contract is verified |
| KIS US ETFs, including GLD/QPUX/DRAM | Unknown; overseas order contract differs from domestic | Unknown | Supervised local SL and trailing, with a verified executable sell route |

The presence of `CNDT_PRIC` is not proof of downside protective SELL support. An
HTS automatic-order feature does not establish an Open API facility. Neither
NXT-only support nor ETF exclusion is inferred from incomplete documents.

Before entry, select `sl_provider` and `trailing_provider` independently, record the
selection and explain it in preview. Local fallback is an explicit mode: a running
worker, fresh price feed, durable state, known exit route and session policy must
all be ready before entry. A native stop plus local trailing is valid; both being
local means a worker outage leaves no broker-held price protection. That limitation
must be visible to the operator. Provider migration requires reconciliation and a
versioned ownership handoff; never run two active exit owners for one position.

## 3. Entry and protective lifecycle (MV3)

1. Resolve instrument, environment, eligibility, signal history and execution
   quote. Read complete account/position/order/buying-power snapshots. Never apply
   the HL operating-capital multiplier to KIS cash purchasing power.
2. Validate cash/margin, lot/tick precision, minimum order size, currency/FX,
   concentration and correlated exposures (SPY/UPRO/SP500; QQQ/TQQQ/XYZ100), maximum
   per-trade loss, spread and allowed trading session. Risk limits must be explicitly
   configured; no implementation default may turn missing limits into unlimited.
3. Persist the trade plan, stop/trailing policy, unique intent and supervisor
   readiness before transmission. Preview is default and makes no signed write.
4. Submit through the selected venue adapter. Persist an attempt before network
   transmission. An acknowledgement is neither a fill nor an active stop.
5. On every actual partial fill, establish/resize protection for the observed
   exposure. Record the first-fill-to-covered interval. Enforce a configured
   maximum unprotected interval; cancel residual entry intent and invoke the
   predeclared bounded risk-reduction policy if protection cannot be established.
   If a broker cannot close at that time, enter intervention and retain exposure
   visibly; never report it as protected or flat.
6. Confirm order status, quantity and trigger semantics through venue readback;
   local SL/trailing readiness is separately recorded. Only verified coverage and
   reconciled fills allow the normal protected state. A rejected grouped child or
   partially filled parent is not covered merely because a bracket was requested.
7. Track the execution-instrument price using the selected provider. A trailing
   threshold may tighten, never loosen for a long. A fresh tick crossing the floor
   persists one exit intent. Rebound does not erase that intent.
8. Route native/local/manual exit events through one account/instrument coordinator.
   Observe native execution, reserved/available quantity and pending sales. HL uses
   reduce-only where supported. KIS requires cash sellable quantity and explicit
   order reservation; it must never emulate reduce-only by sending two full sells.
9. For KIS cancellation-before-local-exit, query cancellation terminality and fills
   before a replacement sale. Treat late partial fills as new reconciliation input.
   Cancellation changes protection coverage: record the gap and apply its bounded
   policy. If cancellation outcome is unknown, do not issue a competing sale.
10. Reconcile positions and every managed order/attempt to terminal outcomes.
    A flat balance with a live sell order still requires cleanup. A disappeared
    open-order row does not prove fill/cancel; use history and executions.
11. Persist operational completion without waiting for journal publication. On a
    user request or scheduled journal run, finalize only after flatness, relevant
    terminal orders and reconciled costs; recover incomplete work idempotently.

Grouped HL entry/SL can be added after its precise activation behavior is tested;
it must not bypass per-fill coverage checks. Current local trailing enrollment
requires a fully filled single protected long and is not a partial-entry manager.
Use a separate entry/protection coordinator before handing off to that manager.

Broker positions are netted by venue/account/environment/instrument, not strategy.
The initial version permits exactly one active strategy-owned position cycle per
that key. Reject a second strategy's entry before sending, including concurrent
requests, with a transactional ownership constraint. Transfers/manual positions
are not adopted implicitly. A future shared-instrument multi-strategy mode would
require a separately specified allocation ledger and protection attribution.

## 4. Failure, restart and operating policy (MV3)

- **Uncertain submit:** persist UNKNOWN, query by native/client IDs and fill history;
  do not blindly resend. KIS idempotency is application-owned unless documented
  otherwise; missing broker evidence requires intervention rather than inference.
- **Network gap/stale feed:** stop new entries and watermark updates; retain native
  orders. Local protection cannot execute without a working connection. Record
  degraded health and alert; do not promise a precise stop fill.
- **Protection rejected/expired:** prevent adds and fresh entries, preserve useful
  confirmed coverage, resolve pending orders and apply the configured exit policy.
- **Session close, holiday, DST, halt or limit move:** independently evaluate signal
  and execution calendars. KIS protection may not execute out of session. Expiring
  orders need explicit renewal and overnight policy; closed markets cannot be
  solved by labeling an exit as a market order.
- **Native stop-limit triggered but unfilled:** expose triggered/open status;
  apply the configured escalation policy only with a verified venue order type.
- **Restart:** acquire account ownership; restore SQLite intents; fully paginate
  orders/fills/positions; verify protection and cost cursors; resume only after
  consistent snapshots. Unknown/manual positions remain outside automatic
  protection ownership until explicitly adopted; journal ingestion includes them.
- **Multiple positions:** existing trailing holds one process-wide account lock per
  position worker. The planned account supervisor owns one lock and multiplexes
  positions; this is required before concurrent BTC/ETH/ETF management. No multi-host
  execution is claimed. Do not launch one existing worker per position on one account.
- **Manual interference:** reconcile reductions; additions, reversals or foreign
  orders stop automated management until ownership is resolved.

Numerical budgets (quote age, protection grace, retry count/deadline, slippage,
price bands, per-position/portfolio risk) are required strategy settings. Validation
must reject missing or contradictory values. Do not quietly inherit the existing
trailing worker's 3-attempt/120-second limits as a universal multi-venue policy.

## 5. Modules, state and CLI boundaries (MV5)

Proposed thin adapters extend `kis_hl/kis/client.py` and
`kis_hl/hyperliquid/client.py`. Domain logic stays outside transport. Candidate new
modules: `instruments.py`, `capabilities.py`, `execution.py`, `protection.py`,
`account_supervisor.py`, `execution_storage.py`, `journal_reconciler.py`.
Future signal/notification modules may add `signals.py` and `notifications.py`;
keep strategy evaluation, notification delivery and order authority separate.
Reuse existing risk, session, trailing and journal components where contracts fit.
Do not rewrite working modules to impose a generic broker abstraction prematurely.

SQLite adds versioned tables for instrument mappings, capability evidence,
strategy/trade plans, order intents/attempts, immutable venue fills, position cycles,
protection coverage/events, reconciliation cursors and journal outbox records.
Additional proposed state includes sync runs/coverage gaps, source revisions,
cycle attribution, versioned signals, notification attempts and execution grants.
Unique keys include venue/account/environment and native execution identity.
Store decimals as strings, UTC timestamps with source timezone/session metadata,
and external account references without credentials. Existing journal rows and
trailing tables remain readable; migrations and rollback are planned per increment.

Proposed CLI surfaces, not yet implemented:

- `instrument list/verify`, `capability inspect/verify`, `chart fetch`.
- `account positions/orders/fills/buying-power` with full pagination.
- `order preview/submit/status/cancel/amend`, defaulting to no exchange mutation.
- `position protection/status`, `supervisor run/status/recover`.
- `journal sync/status/reconcile/import`, with account/date scope and preview.
- `strategy inspect/evaluate`, `signal list/show/execute`, `notification list/retry`.

Maintain `kis-account` compatibility. A `--live` flag selects authorized execution
only after all gates; it does not override capability, quantity or session errors.
KIS and HL credentials/environments remain separate. Broker-reported errors are
normalized without exposing account numbers, tokens or secrets.

## 6. Journal contract (MV4)

Use the [trade-journal skill](../.agents/skills/trade-journal/SKILL.md) and its
[record contract](../.agents/skills/trade-journal/references/record-contract.md) /
[statistics](../.agents/skills/trade-journal/references/statistics.md) as the owners.
Do not duplicate or redefine the nine formulas here.

A cycle is flat → entry/adds/reductions → flat for one venue/account/environment
and instrument. Strategy is attribution, not a filter on whether a fill exists.
Actual KIS/HL execution history is authoritative, including agent, HTS, web, native
stop and liquidation executions. Local order intents and agent conversation are
supporting evidence, never proof of a fill. Read all configured account scopes,
including explicitly selected HL subaccounts and HIP-3 instruments; never use an
API wallet's empty history as proof that the user's account has no trades.

Ingestion is independent of live asset eligibility and protection enrollment.
An external fill in an unsupported execution asset still belongs in the ledger;
unresolved instrument identity blocks its accounting finalization, not its import.
Read-only sync never submits, cancels or adopts a position, and does not retroactively
claim that an external entry had SL/trailing protection. Execution policy remains
one strategy-owned cycle per account/instrument; outside trades can still mix with
it in the broker's net position and must be reconciled as actual exposure.

Link fills to a local intent only using supported native order/client identifiers.
Store `origin` as agent/HTS/web/other/unknown only when evidenced; absence of a local
ID means external-or-unknown, not proof of HTS versus web. Capture harness name,
strategy/version, signal ID and rationale when known. Unknown strategy is
`unassigned`; mixed origins/strategies are marked `mixed` and require attribution
review. Keep such completed cycles in the account journal but out of a named
strategy's edge statistics. Do not guess strategy from ticker or timing, create
fictional lots, or double-count manual and automated portions of a net cycle.

Journal synchronization is on demand or scheduled; it is not an order-path latency
requirement. The user-selected default is `journal.sync_interval = 3h`, configurable through
validated settings; every scheduled run ingests history and reconciles eligible
closed cycles. User-requested sync runs immediately without waiting for that timer.
An optional daily review digest and KIS session-close cost follow-up are separate
policies. This planning task does not install a running schedule. Reject zero,
negative or malformed intervals and retain the last valid configuration. Persist
last success/next due time; interval changes affect the next run without resetting
coverage cursors. On restart, coalesce missed ticks into one catch-up run, not a
burst of duplicate jobs.
Adapt ingestion frequency to activity, API limits and retention. Trading protection
continues on its own real-time schedule; it must never wait for the journal job.
The scheduler invokes the same CLI/domain service without requiring an interactive
agent session. Serialize overlapping sync runs per account/environment.

For each run, freeze an end time, fully paginate bounded windows, retain overlapping
replay, and deduplicate by the documented native execution identity plus account/
environment. An order ID alone is insufficient for partial fills. Validate KIS
row identity and whether an endpoint reports increments or cumulative executions;
never sum cumulative order totals as fresh fills. Use unaggregated HL fills.
Handle equal timestamps explicitly; do not advance past a saturated timestamp
boundary and silently lose trades. Commit normalized facts and the completed
coverage cursor atomically. A timeout, invalid page, retention gap or unrecoverable
boundary leaves that interval incomplete, even if later pages/accounts succeed.

On first sync, recover a known-flat boundary or documented opening inventory with
cost basis. A current zero balance alone cannot reconstruct missing closed cycles.
Missing opening history, fees or funding stays `JOURNAL_PENDING` with an actionable
reason. When API history is insufficient, support an explicit broker/exchange
statement import with provenance, identity matching and duplicate checks; never
claim complete history merely because pagination ended. Report last successful
sync, covered interval, gaps, new/duplicate fills, open/pending/finalized cycles,
attribution issues and corrections. Daily reconciliation compares observed holdings
with the fill ledger and separately explains corporate actions and transfers.

Deduplicate closed cycles independently from fills. Weighted entry/exit prices use
actual fills; net realized PnL includes intended commissions, taxes, funding and
other costs. HL `closedPnl` is not assumed to be net of all those costs; a total fee
that includes a builder fee must not have that fee added again. Explicit net PnL
must not have fees subtracted twice. Open positions never enter realized statistics;
partial exits are retained for eventual completion. An external reversal crossing
zero splits the execution at zero into closing/opening portions with conserved
quantity and allocated fees, or remains pending until that rule is implemented.
Paper intents are not realized trades; testnet records are isolated from live.

Persist completed-cycle revision and journal outbox atomically, then idempotently
write the record plus required statistics snapshot. A later sync may ingest a new
cycle while an older one awaits costs; only orders related to that cycle gate its
finalization. Corrections retain the original source revision and append an audited
superseding record; current aggregates count only the effective revision. Preserve
historical `stats_json` snapshots and expose changed current statistics explicitly.
Before import/finalization, detect potentially overlapping legacy `journal add`
records; require explicit linkage/supersession rather than duplicate performance.

Add explicit settlement/reporting currency and conversion timestamp/source before
combining KRW, USD and USDC portfolio PnL. Never sum unlike currencies. Percentage
statistics remain unweighted and strategy-specific per skill. Transfers, dividends,
splits and dust require separate reconciliation rules, not fabricated trade fills.

## 7. Harnesses, future strategy signals and notifications (MV5)

Codex, Claude Code and Hermes call the same preview, execution and journal CLI;
no harness-specific authority or account state is authoritative. Direct HTS/web
orders bypass this coordinator and are observed via venue history. The existing
protection guarantees apply only to system-managed entries, not to those external
orders. Their later discovery can raise a coverage alert without taking ownership.

Strategy skills do not yet exist. A future registered skill defines a versioned
strategy contract and evaluation cadence; evaluation may use a harness or a
deterministic evaluator, but produces validated structured signals. Persist the
strategy/version, evidence-bar IDs/time, signal/execution instrument, direction,
reason, creation/expiry time and proposed risk/protection policy. Skill text or
model output cannot supply its own execution grant or bypass the risk coordinator.
Deduplicate signal events by strategy/version, instrument, evaluation interval and
trigger identity; repeated polling must not turn one opportunity into many entries.

| Mode | Signal handling | Authority to execute |
| --- | --- | --- |
| Observe | Persist signal and notify | No order |
| Manual request | Notify, then operator requests a named signal through a harness/CLI | Authenticated request bound to a current preview and signal |
| Automatic | Persist notification event, attempt delivery, then evaluate the configured grant | Prior explicit strategy/account/instrument policy; no new per-trade confirmation |

Default until configured is observe/manual request. An automatic grant specifies
account/environment, allowed strategy revision/instruments/sides, size and risk
limits, sessions, expiry and notification-failure policy. Recommend blocking fresh
automatic entries if the configured notification channel rejects/times out; an
operator may explicitly choose a bounded alternative. Record API acceptance
separately from human acknowledgement. Neither requires delaying an existing SL,
trailing exit or other already authorized protective action.

Immediately before sending in either execution mode, recheck signal expiry, current
prices, available funds, positions/open orders, capability and supervisor readiness.
Changed preview parameters invalidate prior manual authorization. Claim execution
atomically against the signal ID so manual and automatic paths cannot both submit.
An uncertain attempt is reconciled by the order coordinator, not retried as a new
signal. A kill switch blocks new entries while protection and reconciliation run.

Use a local SQLite notification outbox/inbox as the durable record and pluggable
delivery adapters. Recommended first channel is a private Telegram bot chat; ntfy
is an alternative for dedicated/self-hosted push, and Slack fits an existing team
workspace. See the [notification evidence and tradeoffs](../docs/product/trading-notifications.md).
Channel choice and credentials remain unconfigured. This task sends no messages.

Notify promptly for strategy opportunities and protection/ownership failures; use
digests for journal completion and daily review. Include event ID, strategy/version,
instrument/venue, reason, expiry, mode and a reference to the current local preview.
Mask account references and omit credentials/full balances. Retry transient delivery
errors with bounds/backoff, expire stale opportunities and retain failed attempts.
Delivery is at-least-once where external APIs lack idempotency: a timeout may create
duplicate messages, but never duplicate order intents. No message delivery implies
that a person saw it. Optional acknowledgement is separate from trade permission.
Initial Telegram integration is outbound only; optional authenticated response
buttons/commands need a later adapter with user/chat allowlists, one-time expiring
signal-bound requests and the same execution gates. No unauthenticated callback or
arbitrary chat command may directly invoke an order.

## 8. Implementation gates still unresolved

- Exact KIS domestic/US order enum and protection semantics, including target ETF
  eligibility, side comparator, reference feed, expiry and effective-date changes.
- KIS account entitlements, US quote/order exchange routing (including DRAM/Cboe),
  current NDX code and required chart depth/cadence.
- Exact HL contract metadata/underlying and eligibility for every proposed route;
  no symbol alias or asset expansion is authorized by this document alone.
- Confirm whether QPUX/DRAM issuer identities match the user's intended products;
  choose strategy signal rules, ATR/cadence, risk and overnight settings.
- Operational supervision, sync cadence/retention coverage and alert destination.
  Confirm account-history inclusion of HTS/web executions with read-only samples;
  validate statement import, KIS row identity and cost availability per market.
  Local protection availability is
  an explicit runtime dependency; no unattended guarantee is made.

These gates block enabling the affected live route, not completion of this design
with its uncertainty recorded. Subsequent implementation starts with verification
and paper/replay slices; any actual order test needs separate authorization.
