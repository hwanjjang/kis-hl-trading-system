# Protected trading operations

This implementation is CLI-first and uses one local SQLite database. Codex,
Claude Code, Hermes and a person can invoke the same commands. Notification
delivery is excluded. No services are installed automatically.

## Instruments and source identity

Use `instrument list`, `instrument verify --instrument ID`, and
`capability inspect --instrument ID`. Index and execution IDs are separate.

| Analysis | Execution IDs |
| --- | --- |
| `index:KOSPI` (shared timing signal, not a price proxy) | `kis:122630` preferred, `kis:069500` fallback; independently `hl:xyz:KORU` |
| `index:SPX` or `kis:SPY` | `kis:SPY`, `kis:UPRO`, `hl:xyz:SP500` |
| `index:NDX` or `kis:QQQ` | `kis:TQQQ` preferred, `kis:QQQ` fallback; `hl:xyz:XYZ100` |
| Matching crypto | `hl:BTC`, `hl:ETH` |
| Named gold reference | `kis:GLD`, `hl:xyz:GOLD` |
| Quantum basket | `kis:QPUX` |
| Named memory reference | `kis:DRAM`, `hl:xyz:DRAM` (distinct contracts) |

South Korea trade.xyz exposure uses `hl:xyz:KORU`; `KR200` and `EWY` remain
excluded. KORU references a leveraged ETF, not an equivalent KOSPI200 contract,
and uses U.S. cash-equity hours. The KIS `AMS` / `KORU` mapping supplies quotes
only; it adds no KIS execution instrument. See [asset policy](trade_xyz_assets.md).
KORU live order acceptance and native trailing-stop behavior remain unverified.

KIS DRAM's AMEX order route, USD currency and whole-share lot were observed through
`search-info` on 2026-09-12. That verifies broker metadata, not order acceptance.
The fund's listing is independently documented by
[Cboe](https://www.cboe.com/us/equities/notices/new_listings/details/?early_trading_ipo=false&etf=true&firm_name=Roundhill+Financial+Inc.&first_trade_dt=2026-04-02&ipo=true&symbols=DRAM).
QPUX is the [Defiance 2X Daily Long Pure Quantum ETF](https://www.defianceetfs.com/qpux/).
HL live eligibility still comes from the existing SQLite mapping and recent metadata
verification. Merely appearing in this catalog does not make a HIP-3 asset eligible.
The managed gateway supports verified USDC collateral only.

`chart --instrument ID --date-from YYYYMMDD --date-to YYYYMMDD` returns a vendor
page with source, currency, timezone and adjustment metadata. It explicitly does
not assert complete historical coverage or that today's bar is closed. A future
strategy must verify its required depth; a proxy is never silently substituted.

## Cross-venue timing and preferred execution policy

User requirements (policy, not an implemented automatic router):

- Manage and trade KIS and Hyperliquid independently. Keep account funds,
  positions, order ownership, sizing, risk limits and execution results separate.
- Use `index:KOSPI` to decide entry and exit timing for `kis:069500`,
  `kis:122630` and `hl:xyz:KORU`. Do not silently substitute KOSPI200.
  A shared timing signal does not make these instruments equivalent or permit
  using index points as execution prices, ATR, stops or order quantities.
- Entry and exit decisions are intended to apply on both venues, with separate
  venue-specific execution. This is not an atomic cross-exchange transaction.
- On KIS, prefer `kis:TQQQ` over `kis:QQQ`, and `kis:122630` over `kis:069500`.
  The specified fallback trigger is failure to satisfy the broker's leveraged-ETF
  deposit requirement, not an inferred trend or volatility rule. Do not invent a
  deposit threshold or assume the same requirement across domestic and overseas
  ETFs; use verified account/product-specific broker eligibility. Unknown
  eligibility or an ambiguous order outcome is not proof of deposit ineligibility.
  The fallback still requires its own funds and safety checks. This is a selection
  priority, not an instruction to buy both ETFs. Exit the instrument actually held;
  do not replace an exit with a fallback entry.
- Apply shared strategy entry/exit decisions to all explicitly paired market
  groups, not just KOSPI. The preferred/fallback ETF choices above are KIS-only;
  do not change the independently selected Hyperliquid contract.
- If one venue cannot execute because of its session, funds or a rejected order,
  execute only the eligible venue. Reassess the skipped venue on a new valid
  signal; do not automatically carry the old signal into its next trading session.
- Shared strategy exit signals apply to both venues. Protective stops and
  trailing exits remain account-local and must not cause a peer-venue exit or
  wait for that venue. An unresolved submission must be reconciled before any
  retry or fallback; separate execution does not imply equal or simultaneous fills.

Implementation decisions still requiring confirmation:

- The complete explicit market-pair registry beyond the KOSPI and Nasdaq groups;
  do not infer new leveraged alternatives merely from ETF availability.
- Whether the user's additional "KIS-only" qualification describes only the
  leveraged-ETF eligibility/fallback issue or restricts shared signal origination.
  No signal-origin restriction is implemented on this ambiguous wording.
- Broker evidence for each leveraged product's deposit eligibility; the policy
  does not establish an API field, deposit amount, or live eligibility result.

The current signal/plan path uses explicit execution instrument IDs; it does not
automatically select these fallbacks or coordinate both venues. Do not claim
paired execution until that path is implemented and verified. No new execution
authority, live order or supervisor start is implied by this policy.

## User-approved risk units (requirements, not implemented workflow)

The proposed approval flow is signal -> agent proposal -> user-selected risk units
-> bounded entry and protective management. These requirements do not authorize
live orders, change active plans, or implement conversational approval handling.

Policy reconciliation (2026-09-24): the user's final instruction confirmed
[issue #15](https://github.com/hwanjjang/kis-hl-trading-system/issues/15) as the
risk-unit authority. It supersedes this section's earlier thousand-USDC flooring,
below-1000 guard and undecided cumulative-unit-limit wording from `758a511`.
The target calculation and its implementation gap are owned by the strategy
document's [capital](strategy_execution_design.md#capital-model),
[sizing](strategy_execution_design.md#position-sizing) and
[risk-cap](strategy_execution_design.md#portfolio-risk-caps) sections. No active
plan, live guard or execution authority changes through this reconciliation.

Confirmed user semantics:

- One risk unit is a planned loss at the fixed stop-loss equal to 1% of the
  account's defined operating assets, not a purchase notional of 1% of assets.
  Keep sizing tied to the fixed SL; do not increase quantity merely because a
  tighter trailing exit might close earlier. Separately, #15 permits verified
  improvements in existing stops to free budget for a new tranche; that tranche
  still needs its own fixed-stop sizing and authorization. Costs and execution uncertainty
  must be included in the proposal; realized loss is not guaranteed to stay at 1%.
- "TS starting amount" means position profit required before trailing activation,
  not an instrument price. The user's selected behavior is immediate activation
  without a profit or breakeven prerequisite. A trailing exit at a loss is allowed.
  Do not model this as a zero-profit crossing: it must not wait for fees, spread
  or an initial adverse move to be recovered before starting.
- Immediate activation means the earliest supported, verified point in the
  fill/protection lifecycle, not a claim of atomic entry plus SL plus TS. Preserve
  fixed SL while TS is being established and after activation under the existing
  protection policy. Waiting or acknowledged-but-unverified TS is not active coverage.

Operating assets follow the confirmed #15 target linked above. Hyperliquid uses
the selected perp account's value without the current helper's flooring. Disclose
both operating-capital and unmultiplied-account risk percentages: before rounding
and costs, one unit at the target 10x budget risks 10% of that account value. This
is not an instruction to set exchange leverage to 10x. KIS 1x remains a documented
rule only within #15; it does not add unit sizing to existing KIS order routing.
Account scope, valuation time and currency must be explicit; never pool accounts
or treat buying power as account equity.

Scheduled advisory briefings must include fixed SL, recommended TS percentage,
immediate activation with loss exits allowed, per-unit quantity/notional/risk and
the proposed unit count with available-margin evidence. Under #15 there is no
preset per-asset/portfolio unit cap or add-up count limit; distinguish actual
funds and existing plan constraints from such a policy cap. If margin is short,
report the shortfall for the user's fund-or-skip decision; do not silently add funds
or bypass current execution checks.
Missing evidence must appear as an explicit unavailable field, not invented sizing.
Every scheduled strategy review must also use fresh read-only account state:
holdings, quantities, average entries, valuation/P&L, cash or margin, pending orders
and verified protective coverage. Evaluate hold/add/reduce/exit scenarios against
actual exposure and account-local constraints, not market signals alone. Include
source time and account scope, and distinguish unavailable evidence from empty
positions. Never infer active protection from an acknowledgement or local plan.
This notification requirement does not authorize orders or activate management.

Still unresolved: percentage-trailing configuration through the managed path
and the bounded approval/expiry and
execution-failure contract. The current
managed trailing path still uses frozen ATR quote distance; low-level percentage
support does not establish end-to-end managed support. Implementation and tests are
required before the proposed approval workflow can execute trades. The absence
of preset cumulative unit caps is decided, not an unresolved limit to invent.
Current managed execution remains long-only; #15's symmetric short calculation
and the separate short-trailing follow-up are not claims of working short management.

## Prepare and submit

Create a JSON plan with the following required fields. Numeric prices, sizes and
limits are decimal strings; durations and UTC epoch milliseconds are integers.

| Fields | Meaning |
| --- | --- |
| `intent_id` | Stable unique request ID; cannot be reused after completion |
| `instrument`, `signal_instrument` | Explicit execution and analysis IDs |
| `strategy`, `strategy_version` | Attribution and immutable strategy version |
| `quantity`, `limit_price` | Long-entry size and execution-instrument price |
| `atr`, `atr_multiple` | Frozen execution-instrument ATR(10D) and stop distance multiplier |
| `max_notional`, `max_loss` | Per-entry notional and planned initial loss limits |
| `max_portfolio_notional`, `max_correlated_notional` | Same-account, same-currency gross exposure caps including pending orders |
| `max_spread_bps`, `max_entry_deviation_bps` | Spread and entry-price band limits |
| `max_quote_age_ms`, `protection_grace_ms` | Quote freshness and maximum unprotected observation interval |
| `max_exit_attempts`, `exit_deadline_ms`, `exit_reprice_ms` | Finite submission, cancellation and repricing budgets |
| `slippage` | Fractional price bound for a protective sell limit |
| `allow_local_sl` | Explicit acceptance of worker-dependent SL when native SL is unavailable |
| `expires_ms` | Entry intent expiry; it does not remove protection from an existing position |
| `verified_price_step` | Additionally required for KIS; exact permitted price increment for the selected instrument/session |
| `trailing_provider` | New HL perpetual plans default `native`; KIS defaults `local` |
| `local_trailing_backup` | Defaults true with native: concurrent local nine-minute exits; explicitly false disables backup |
| `harness` | Optional evidenced origin label, such as `codex`, `claude-code` or `hermes` |

Exposure limits are gross notional, not leverage-normalized economic exposure or
a consolidated cross-currency/cross-broker NAV limit. US equity families are
conservatively grouped together; unknown holdings are charged to the proposed group.
All configured limits are mandatory. The existing HL operating-capital multiplier
is not applied to KIS cash balances.

```bash
# Read closed execution-instrument bars and replace ATR in the proposed plan.
python -m kis_hl.cli order prepare --input my-plan.json
# Supply the returned plan object, not the outer response envelope.
python -m kis_hl.cli order preview --input prepared-plan.json
python -m kis_hl.cli --db data/kis_hl.sqlite order submit --input prepared-plan.json
python -m kis_hl.cli --db data/kis_hl.sqlite supervisor run --venue hyperliquid --once
```

The default queue and worker are paper previews. They send no orders and invent
no fills. To execute, both `order submit` and `supervisor run` require `--live`.
KIS environment selection still follows `SANDBOX`; HL follows its configured URL.
The supervisor rechecks funds, exposure, fresh bid/ask, lot/tick, ATR, session,
ownership, authority and the entry kill switch immediately before transmission.

Use the same database path for every trading CLI. One supervisor process owns an
account lock and multiplexes its positions. Do not run a legacy single-position
trailing worker alongside it. The ownership guard also blocks raw HL entry and
legacy enrollment in an instrument already owned by the new supervisor. This is
a local-host contract, not a distributed lock or protection against direct venue UI
actions or applications using a different database.

## Harness-originated entry

[Explore the Hermes entry and management diagram](architecture/hermes-entry.html).
This is the current Hyperliquid **new-entry** path. Hermes supplies a structured
plan through the same CLI as other harnesses; no Hermes SDK integration is required.
The plan must express the user/strategy's authorized size and risk limits, with
`harness: "hermes"` when that origin is evidenced. For a position already entered
outside the system, use [manual position handoff](#manual-position-handoff) instead.

1. Hermes calls `order prepare` for execution-market ATR, then `order preview`
   on the returned plan object. These calls do not submit an order. Preparation
   does not choose the strategy or authorize risk limits for the user.
2. `order submit` validates and persists a `QUEUED` intent in SQLite. The returned
   position ID identifies the request; it is not evidence of an exchange fill.
3. A separately running account supervisor consumes that queue. Immediately before
   entry, it checks current account/market data, ownership, eligibility, risk and
   authority, then persists the normalized native distance and order attempt before
   transmission. Paper requests reach `PREVIEWED` without placing orders.
4. Actual partial fills receive fixed-SL protection. With the new Hyperliquid
   defaults, the same supervisor also runs the local nine-minute backup; after
   terminal entry and verified full fixed-SL coverage it submits native trailing
   once. Verified active readback establishes native trailing coverage; an open
   waiting order is not active coverage. Either policy can trigger an exit, with
   reduce-only local exits reconciling the remaining position and flat cleanup
   cancelling residual protection.

For authorized live execution, both `order submit` and `supervisor run` require
`--live`. Use the same database, configured account and mode. Start one durable
`supervisor run --venue hyperliquid --live` process only if that account's worker
is not already running; `--once` performs one pass and is not ongoing management.
Hermes can inspect progress with `order status --id POSITION_ID` and return to the
user while the supervisor continues. The local backup requires that worker to stay
alive; a conversation session is not the protection loop. See the
[protection contract and rollout limits](#protection-and-controls) for failures,
provider overrides and the still-unverified live exchange contract.

An optional registered-signal path uses `signal execute --id ID --input PLAN --manual` or `--grant ID` instead of `order submit`, and queues into the same
supervisor. Live signal execution also needs `--live`. Signal ingestion alone
never authorizes a trade; the supervisor rechecks signal/grant authority before
entry. See [strategy signals and grants](#future-strategy-skills) for their bounded
authority and external strategy-evaluation boundary.

## Manual position handoff

[Explore the handoff and management diagram](architecture/manual-position-handoff.html).
A harness such as Hermes calls the same CLI; this does not require or claim a Hermes
SDK integration. It supplies explicit account configuration, a shared database,
entry/SL order IDs, a unique intent and an agreed risk plan. A durable supervisor
process, not the agent conversation, owns the ongoing loop.

1. Query the existing long, complete entry fills and open orders. This admission
   supports one fully filled, flat-to-long entry whose original quantity and weighted
   average still match the account. Additions, reductions, foreign orders, missing
   retention evidence and a legacy manager owning the coin block admission.
2. Prepare the plan fields above; quantity and limit_price must equal the actual
   entry quantity and average. `order prepare` can refresh ATR from execution-market
   daily bars. Policy numbers are explicit user/strategy inputs, never invented by
   the harness. Set `harness` to `hermes` when evidenced.
3. Supply an existing full-sized reduce-only native Stop Market SL at or above the
   ATR risk floor. If none exists, establish and verify it separately under the
   chosen policy first; adoption creates no entry or fixed-SL order.
4. Queue the handoff. Without `--live` this is paper-only. The running account
   supervisor can consume it without releasing its process lock:

```bash
python -m kis_hl.cli --db data/kis_hl.sqlite order adopt --input handoff-plan.json --entry-order-id ENTRY_OID --stop-order-id SL_OID --live
python -m kis_hl.cli --db data/kis_hl.sqlite order status --id POSITION_ID
# Start this only if the same account supervisor is not already running.
python -m kis_hl.cli --db data/kis_hl.sqlite supervisor run --venue hyperliquid --live
```

`ADOPTING` means queued, not protected by this system yet. Under the account lock,
the supervisor checks current risk/ATR, original ledger, quantity/average, eligibility,
existing SL and ownership, then atomically imports the two known order IDs and marks
`PROTECTING`. The next reconciliation submits native trailing once, while the same
worker runs the local backup. `PROTECTED` still requires verified active native
coverage. Fixed SL persists throughout. Local tracking starts at admission; earlier
highs are not reconstructed, and native tracking starts at exchange activation.

Failed admission stays `INTERVENTION` without imported attempts or broker writes.
After correcting evidence, `order recover --id POSITION_ID` retries admission.
`order cancel` or `order exit` before admission cancels only the handoff; the external
position and orders remain unchanged. These paths never generate a new entry.
After admission, the ordinary exit/recovery/cleanup rules apply. Duplicate intent,
active owners and previously owned native IDs cannot be adopted again. The imported
SL counts as one owned stop for the existing protection attempt budget.

Keep the supervisor alive beyond the harness session using the host's process
manager. Use the same DB and one account supervisor; do not run legacy
`trailing run` for that asset alongside it. Historical legacy registrations remain
local. Imported entry/SL fills retain their original journal attribution; new
supervisor orders can carry the management harness/strategy. Adoption does not prove
that the original manual entry was generated by that strategy. Reconcile/close active
adoptions before rolling back to code without this state support.

## Protection and controls

SL and trailing providers are selected independently. Eligible HL perpetuals use
native reduce-only sell Stop Market protection after actual partial fills, with
native trailing with concurrent local backup by default for new plans. Coverage requires account/order/instrument/side/trigger readback;
an acknowledgement is insufficient. KIS uses local SL and trailing. Neither an HTS
feature, `CNDT_PRIC`, nor a stop-limit label proves protective Open API SELL support.
Hyperliquid documents native trailing for perpetuals. New HL plans normalize an
omitted provider to `"trailing_provider": "native"` and `"local_trailing_backup": true`.
Explicit `"local"` selects local-only management; native with backup false selects
native-only trailing. KIS defaults local and rejects native. Existing persisted
plans retain their settings; absent historical selectors mean local, and an absent
historical backup field does not silently enable a second policy.

Native mode follows the best **continuous mark price** since exchange activation,
using the plan's frozen ATR distance rounded down to the distance's own precision
(metadata decimal tick and five significant figures, with integer exemption).
The normalized distance is persisted before entry; a distance that rounds to zero
blocks entry.
The local backup uses the nine-minute policy below concurrently. Either native
execution or a local threshold breach may begin closing exposure. Local breaches
persist the supervisor's one exit intent and use bounded reduce-only IOC exits;
there is no second worker, automatic provider switch or native retry. Native waiting,
unknown or condition-parser intervention does not suppress an independently triggered
local exit; unrelated account/identity intervention still freezes automation. Pending
exits are reconciled before retry and partial native fills reduce subsequent local
exit quantity. Both exchange protections remain until verified flat cleanup. The supervisor first covers
actual partial fills with fixed native SL orders, then submits one reduce-only
trailing order after the entry is terminal and fixed SL coverage is verified.
The fixed SL remains active to preserve the original risk floor. Waiting for the
entry remainder can delay native trailing activation; it does not delay fixed SL.
Status exposes `providers.trailing` and `trailing_covered_size` separately from
fixed `covered_size`. An acknowledgement alone does not establish coverage.

The adapter uses the `trailingStop` action observed in the official app on
2026-09-22, SDK asset resolution and L1 signing, and ordinary order-ID query/cancel.
The observed action has no client order ID. A timeout or acknowledgement without
a usable native order ID therefore enters `INTERVENTION`: never blindly resend
or adopt another order by matching size/time. Retain fixed SL and reconcile in
the venue before recovery. Explicit rejection also enters intervention without
resending or exiting solely because the trailing submission failed. This native
submission intervention continues fixed-SL monitoring and permits an explicit exit;
unrelated ownership, order identity/type/direction/size and known policy mismatches
still freeze automatic actions. An unparseable trailing condition on an otherwise
validated owned order instead records `trailing_readback_error`, claims zero
trailing coverage, and retains fixed-SL monitoring and explicit exits under native
intervention. Valid matching readback of the same ID restores waiting/active
management without a new submission. Known-ID terminal status still requests a
residual exit even if its condition cannot be parsed. Generic intervention (including
exit-budget exhaustion) clears this exception; temporary transport failure preserves
it so fixed-SL supervision resumes when account reads recover.
A verified full-sized open trailing order with `best waiting` (or omitted best)
remains `PROTECTING` with zero active trailing coverage. Waiting alone never causes
a timeout exit while fixed SL is verified. Active matching readback establishes
trailing coverage. Fixed-SL coverage loss retains its existing grace/exit policy;
termination of an accepted trail still latches a residual exit instead of
recreating a trail with a reset watermark. Flat cleanup requires both
fixed SL and trailing orders to be confirmed terminal. Live acceptance, response
shapes and exchange execution have **not** been exercised; unexpected condition
formats never count as trailing protection. See the [API contract](../.agents/skills/hyperliquid-api/references/exchange-endpoint.md#native-trailing-stop).

Existing positions are never migrated automatically. Before rolling back to a
version without native support, reconcile and close native-managed positions and
their owned orders. Switching an active plan to local is not a recovery action.

The existing trailing rule is preserved: initial floor equals actual entry minus
frozen ATR distance; complete continuous nine-minute buckets can raise the
watermark. The long threshold never decreases. Restart/disconnection discards
the partial bucket; a latched exit survives a rebound and process death.

```bash
python -m kis_hl.cli order status --id POSITION_ID
python -m kis_hl.cli order cancel --id POSITION_ID
python -m kis_hl.cli order exit --id POSITION_ID
python -m kis_hl.cli supervisor pause-entries --venue kis
python -m kis_hl.cli supervisor status --venue kis
python -m kis_hl.cli order recover --id POSITION_ID
```

`cancel` cancels the entry remainder and retains protection for filled shares.
`exit` latches a request for the live supervisor to reconcile and close exposure.
These commands change durable control intent; an already running live worker may
act on them. `amend --id ID --input FILE` replaces only an unsent queued plan.
Active orders require cancellation and source-confirmed reconciliation before a
new request. `recover` requires an intervention state and retains all budgets;
it cannot authorize an uncertain duplicate order or reset an exhausted budget.

Each attempt is committed before network I/O. Unknown outcomes are queried, never
blindly resent. Residual entries and resting exit limits must be confirmed terminal
before competing sales. KIS exits use observed sellable quantity and bounded cash
limits; HL exits are reduce-only IOC limits. Bounded failure remains visible as
`INTERVENTION`. A later flat observation still allows cleanup of known owned stops.
Manual additions, reversals or foreign orders halt automatic ownership; reductions
are reconciled. External positions are not implicitly adopted.

KIS local protection cannot execute during an outage, holiday, halt, closed session
or an unfillable price limit. The weekday/session gate alone is not a complete
holiday calendar; fresh source prices and successful broker reads are also required.
Domestic REST quotes need a current-session trade date. Overseas REST quote receipt
timestamps are interpreted in KST, separately from the US execution calendar, based
on the observed broker response; validate that clock during an in-session rollout.
Native protection remains at the venue during local outages, subject to venue rules.

## Actual-history journals and the three-hour scheduler

```bash
python -m kis_hl.cli journal sync --venue hyperliquid --start-ms START_UTC_MS
python -m kis_hl.cli journal sync --venue kis --start-ms START_UTC_MS
python -m kis_hl.cli journal configure --venue kis --interval-seconds 10800
python -m kis_hl.cli journal run --venue kis --start-ms START_UTC_MS
python -m kis_hl.cli journal status --venue kis
python -m kis_hl.cli journal report --venue kis
python -m kis_hl.cli journal reconcile --venue kis
```

The persistent default is **10800 seconds (3 hours)**. Positive integer changes
affect the next due time; missed ticks coalesce into one catch-up. `sync` runs on
demand. Run one `journal run` process per account under your process manager;
restart it with the same database. This PR supplies the worker, not an installed
system service. Its cadence is independent of the real-time protection worker.
`--start-ms` fixes an explicit initial backfill boundary; later runs replay an
overlap from reconciled coverage. Remove the initial argument after establishing
the desired history, or retain it deliberately for repeated full backfills.

HL imports unaggregated native fills from all execution origins, independently of
the live asset allowlist. Current retained-tail evidence bounds automatic coverage;
older windows remain explicit gaps. A saturated millisecond or missing retention
history requires statement backfill. Funding is included and builder fees are not
added twice. Unresolved spot identity or non-USDC fees are retained as snapshots.

KIS daily execution inquiries return cumulative order summaries without guaranteed
per-execution timestamps and complete fees. They are retained as source snapshots,
not fabricated fills. **KIS automatic journal finalization therefore requires a
source execution/cost statement import.** The collection scheduler still runs every
three hours and exposes this pending reason. Native SL and KIS statement details
remain release verification limits, not claims of live-tested behavior.

Statement JSON schema version 1 has `source`, `start_ms`, `end_ms`, `complete`,
`costs_complete`, `fills`, and optional `costs`. Each fill needs `execution_id`,
`symbol`, `time_ms`, `side`, `quantity`, `price`, `currency`, and reconciled `fee`.
The first execution of a known-flat cycle has `position_before: "0"`. Optional
fields include native `order_id`, evidenced `origin`, `strategy`, `strategy_version`,
`harness`, and `signal_id`. A cash cost needs `event_id`, `symbol`, `time_ms`,
`currency`, and `amount` (positive expense, negative income). Fees/taxes included
in fill fees must not also appear as cash costs.

```bash
python -m kis_hl.cli journal import --venue kis --account ACCOUNT --environment live --input statement.json
python -m kis_hl.cli journal report --venue kis --account ACCOUNT --environment live
```

Import/report/configuration can use explicit account/environment without API
credentials. The operator supplies and verifies statement account and coverage.
Conflicting fills require `--allow-corrections`; revisions and historical snapshots
are retained. Completed net position cycles use actual weighted prices and the
existing nine-statistic contract. Unknown costs/opening history stay pending.
Mixed/unassigned attribution remains in the account report, separated from a named
strategy's statistics. Legacy manual records are unchanged; potential time/symbol
overlap is flagged instead of silently duplicating them. `reconcile` compares
observed holdings with the ledger; it never invents transfers or corporate actions.

## Future strategy skills

`strategy register --input FILE` accepts immutable ID/version, description and an
explicit instrument set. A skill or harness supplies a structured signal through
`signal ingest --input FILE`; this does not grant order authority. Signals have
immutable IDs, strategy/version, analysis/execution IDs, observation/expiry times and
rationale. No arbitrary strategy code, prompt or shell text is executed by this module.

`signal execute --id ID --input PLAN --manual` is an explicit manual request.
Alternatively, `strategy grant --venue VENUE --input GRANT [--live]` creates a
revocable account/mode/strategy/version/instrument grant with `expires_ms`,
`max_intents`, and `max_notional`. Use `signal execute ... --grant ID` for that
bounded automatic path. A reserved slot can be consumed by a crash before enqueue;
it cannot produce an extra trade. Revocation blocks future entry, not an order
already transmitted. The live supervisor rechecks authority after account reads.
Strategy evaluation/timing and notification transports remain external extension
points until the requested strategy skills and notification choice exist.

## Rollback and verification

Pause new entries first. Preserve the SQLite file, reconcile residual orders and
positions, and retain useful native stops. Do not delete state or stop a KIS local
protection worker while treating its positions as protected. Old CLI/storage remain
available, but must not take ownership concurrently.

Run `python3 -m unittest discover -s tests -t . -q` and
`python3 scripts/smoke_protected_trading.py`. The smoke uses temporary SQLite files,
fixture identities and real offline CLI subprocesses. No real order is exercised.
Read-only KIS route probes are documented in the SDLC evidence. Live order acceptance,
gap fills, broker cancellation/reservation races, and in-session quote clocks need
a controlled venue rollout before production reliance.

Native Hyperliquid stop-market payloads keep the trigger and execution price
separate. The sell execution price uses the plan's slippage below the trigger,
rounded upward to a valid tick so the configured price bound is not exceeded.
This follows the separate `trigger_px`/`sl_px` contract in the
[official SDK example](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/examples/basic_tpsl.py).
A bounded market exit can still leave residual quantity after a gap; the supervisor
continues actual-position reconciliation and bounded exit recovery.

Journal collection locks are held only during a collection transaction, allowing
on-demand sync while the periodic worker is idle. A busy periodic worker retries
on its next poll. Hyperliquid native-order evidence may enrich unknown attribution
through an append-only fill revision; a later unknown observation cannot erase it.
Execution amounts, costs, times and conflicting known attribution still require
explicit correction imports.

### Read outages and recovery limits

A transient account snapshot `RuntimeError`/`OSError` puts active protection in
DEGRADED and continues readback. Three consecutive failures, or a read outage lasting
`protection_grace_ms`, latches an exit and reports INTERVENTION while reads continue.
Once consistent fresh account data returns, this read-outage intervention resumes
bounded cancellation/exit automatically. Existing identity/ownership interventions
remain manual. No order is sent using a failed snapshot; the original protection
and exit clocks are not reset. Events retain the failed operation, exception class
and retry count without copying potentially sensitive transport error payloads.

For Hyperliquid, `max_quote_age_ms` also bounds each action's `expiresAfter` from
its durable attempt creation, including stops and exits. Use a realistic network
budget: an expired local send can remain UNKNOWN, and the system never guesses
that it was not transmitted. `order recover` retries reconciliation; it cannot
attest non-transmission or bind an operator-supplied broker order ID. If native
readback cannot resolve an UNKNOWN attempt, inspect broker orders/fills/holdings
and manage any exposure in HTS or the exchange UI. Keep the intent reserved and
do not edit SQLite to retry it. An audited broker-evidence binding workflow is
still required before relying on unattended KIS entries after ambiguous acknowledgments.

Every scheduled collection attempt, including incomplete coverage or an API
failure, advances the next scheduled attempt by the configured interval. It does
not advance successful coverage or fabricate journal completion. `journal status`
shows `last_attempt_ms`, `last_reason`, and `last_success_ms`; explicit `journal sync`
can retry sooner. Interval changes use the last attempt as their scheduling anchor.
A successful historical collection uses its completion clock for scheduling, not
its historical end date. KIS snapshots reuse the date window captured with their
preflight baseline, including intents queued across a day boundary.

Conservative journal discontinuities may leave subsequent cycles pending until a
source correction or complete backfill reconciles the gap; automatic re-anchoring
after an already-known position discontinuity is a follow-up. Architecture HTML
views describe the target design; implementation status and excluded future
notification nodes are mapped in `docs/architecture.md` and the fidelity report.

## Canonical data pipeline

Use the [unified data operations](unified-data-operations.md) for immutable raw
imports, revised market history, account/currency journals and pinned analysis.
These read-only exchange collectors do not adopt positions or place orders.
Keep the same operational database path; existing account execution locks and
managed/trailing state remain authoritative. Canonical reports use canonical
facts only; legacy reports are comparison baselines, never additional trades.
