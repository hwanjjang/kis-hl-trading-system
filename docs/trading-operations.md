# Protected trading operations

This implementation is CLI-first and uses one local SQLite database. Codex,
Claude Code, Hermes and a person can invoke the same commands. Notification
delivery is excluded. No services are installed automatically.

## Instruments and source identity

Use `instrument list`, `instrument verify --instrument ID`, and
`capability inspect --instrument ID`. Index and execution IDs are separate.

| Analysis | Execution IDs |
| --- | --- |
| `index:KOSPI` or explicitly `index:KOSPI200` | `kis:069500`, `kis:122630` (KOSPI200 funds) |
| `index:SPX` or `kis:SPY` | `kis:SPY`, `kis:UPRO`, `hl:xyz:SP500` |
| `index:NDX` or `kis:QQQ` | `kis:QQQ`, `kis:TQQQ`, `hl:xyz:XYZ100` |
| Matching crypto | `hl:BTC`, `hl:ETH` |
| Named gold reference | `kis:GLD`, `hl:xyz:GOLD` |
| Quantum basket | `kis:QPUX` |
| Named memory reference | `kis:DRAM`, `hl:xyz:DRAM` (distinct contracts) |

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

## Protection and controls

SL and trailing providers are selected independently. Eligible HL perpetuals use
native reduce-only sell Stop Market protection after actual partial fills, with
local trailing. Coverage requires account/order/instrument/side/trigger readback;
an acknowledgement is insufficient. KIS uses local SL and trailing. Neither an HTS
feature, `CNDT_PRIC`, nor a stop-limit label proves protective Open API SELL support.
Native trailing remains unverified for both venues.

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
