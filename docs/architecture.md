# Architecture

## Goals

The system has three responsibilities:

1. Collect reference market data through KIS and store raw payloads for traceable analysis.
2. Coordinate protected KIS cash and Hyperliquid BTC/ETH or eligible trade.xyz orders.
3. Reconcile actual account history into deferred, source-backed trade journals.

The project favors a narrow CLI-first shape before adding daemons or strategy automation.

## Components

`kis_hl.config` loads `.env`, validates account and key selection, and separates KIS sandbox/live credentials from Hyperliquid key profiles.

`kis_hl.kis.client` wraps KIS REST calls. It caches OAuth tokens on disk, throttles token refreshes, retries rate-limit responses with backoff, and exposes market-data, paginated account history/balances/orders, and dry-run-default cash order/cancel/amend adapters. POST outcomes are never blindly retried. The `kis-account` CLI outputs only a masked account and whitelisted summary amounts; it does not persist balance data.

`kis_hl.kis_mappings` converts curated trade.xyz assets into KIS quote routes. It keeps RWA trading eligibility separate from KIS market-data availability, so an asset can be Hyperliquid-tradable while its KIS route is still `unsupported`.

`kis_hl.reference_mappings` maps selected trade.xyz assets to secondary reference-data providers. The first provider is Yahoo Finance chart data for commodity, FX, and index cross-checks where KIS is unavailable or needs a fallback.

`kis_hl.kis_collector` executes mapped KIS routes for one symbol or a batch, stores raw payloads in SQLite, and reports per-symbol success, skipped, and failed states without stopping the whole batch by default.

`kis_hl.reference_collector` executes secondary provider routes, currently Yahoo Finance chart quotes, and stores normalized payloads in the same `market_ticks` table.

`kis_hl.daily_collector` collects historical daily OHLCV bars for tradable trade.xyz assets. It uses Yahoo reference mappings for commodity, FX, and index assets and exchange tickers for stock and ETF assets, then upserts rows into `market_daily_bars`.

`kis_hl.xyz_market_collector` snapshots the live Hyperliquid `xyz` universe, collects funding-rate history, and stores top-of-book spread snapshots. Universe asset rows also store Hyperliquid 24h base volume, 24h notional volume, and open interest when present. This keeps newly listed trade.xyz markets visible without immediately making them live-tradable.

`kis_hl.risk` implements deterministic strategy risk calculations: operating capital from Hyperliquid portfolio value, ATR from daily bars, 30-week EMA trend status, asset-class `N` defaults, and per-tranche position sizing.

`kis_hl.signals` implements deterministic signal rules. The first signal is a BTCUSDC futures 3H previous-high close breakout, which returns a long-entry intent.

`kis_hl.btc_strategy` turns Hyperliquid BTC spot websocket mids into 3H spot candles, creates a BTC perp long-entry plan when the latest closed candle close breaks the previous high, sizes the entry from an `80 USDC` notional, and attaches a reduce-only stop-market order at `entry_price - ATR(10D) * 2`.

`kis_hl.trade_journal` creates completed-position journal records and calculates the required review statistics from net return percentages rather than currency PnL. The formula, breakeven, ratio, and holding-day contract is owned by `.agents/skills/trade-journal/`.

`kis_hl.trading_hours` maps tradable assets to the underlying market session group and returns timezone-aware session decisions. Live non-reduce-only trade.xyz orders fail closed outside that session unless `--allow-outside-session` is passed. Reduce-only exits are allowed outside the entry session.

`kis_hl.streaming` provides a reconnecting websocket runner with subscription replay, bounded reconnect backoff, heartbeat support, and stale-stream detection.

`kis_hl.kis.ws` provides KIS websocket subscription payloads, approval-key acquisition through `KisClient`, KIS ping echo handling, and normalized price ticks for domestic and overseas trade feeds.

`kis_hl.hyperliquid.ws` provides Hyperliquid websocket subscription payloads, heartbeat ping support, default REST-to-websocket URL derivation, and normalized `allMids` ticks.

`kis_hl.hyperliquid.client` wraps Hyperliquid public info calls with standard HTTP, including wallet asset state reads for the configured address, and uses `hyperliquid-python-sdk` only for signed trading. This avoids custom signing code.

`kis_hl.binance.client` wraps Binance USDⓈ-M futures REST calls with standard HTTP: public exchange info, mark/index price and funding, top of book, and klines, plus HMAC-SHA256 signed read-only account, position, and order reads. It also owns the `listenKey` lifecycle (create, keepalive, close) for the user data stream. It places no orders.

`kis_hl.binance.trading` extends the REST client with guarded order placement for USDⓈ-M futures: MARKET/LIMIT entries through `/fapi/v1/order`, server-side `STOP_MARKET` (closePosition) and `TRAILING_STOP_MARKET` through the Algo Order API (`/fapi/v1/algoOrder`), and cancel for both. Outcomes are `submitted`, `rejected` (4xx), or `unknown` (5xx / transport failure, reconciled once by client id). Every method validates and rounds against exchange filters, returns a dry-run submission by default, and only on `--live` walks the allowlist, credential, one-way-mode, and account-lock guards before the signed request. `POST /fapi/v1/order/test` is exposed as an explicit exchange-side validation.

`kis_hl.binance.ws` provides Binance combined-stream URL building for `markPrice`, `bookTicker`, `kline`, and `aggTrade` (routed to `/public` for `bookTicker`/`depth` and `/market` for the rest), a market stream client over `kis_hl.streaming`, a user data stream client that requests a fresh `listenKey` per connection, renews it every 30 minutes, and reconnects on `listenKeyExpired`, and parsers that turn market frames into `PriceTick`s and `ORDER_TRADE_UPDATE` frames into normalized order events.

`kis_hl.assets` normalizes user-facing symbols into Hyperliquid L1 names. `BTCUSDC` resolves to `UBTC/USDC` spot, while explicit futures aliases such as `BTCUSDC-PERP`, `BTC-PERP`, and `BTCPERP` resolve to the Hyperliquid `BTC` perp coin. Live spot orders resolve the pair through `spotMeta` to the `@index` order coin. trade.xyz assets resolve to `xyz:ASSET`.

`kis_hl.storage` persists raw KIS payloads, daily OHLCV bars, order submissions, venue order-status events (`order_events`), reduce-only stop-market protective orders, completed trade journal entries, trade.xyz asset rows, Hyperliquid verification checks, KIS market-data mapping rows, secondary reference-data mapping rows, live `xyz` universe snapshots, funding-rate rows, and spread snapshots in SQLite. Raw payloads are stored because vendor schemas and exchange responses can change.

`kis_hl.trade_xyz_assets` defines the curated trade.xyz asset mapping seed. `trade_xyz_assets` rows in SQLite drive RWA eligibility: non-IPO assets and stocks listed for less than 30 weeks are excluded, `KR200` and `EWY` are excluded in favor of `KORU`, and `EWJ` is excluded in favor of `JP225`. KORU is a leveraged ETF reference using U.S. cash-equity hours, not an equivalent KR200/KOSPI200 contract. Its KIS mapping supplies quotes only; it does not add a KIS execution instrument. See [asset policy and seed refresh](trade_xyz_assets.md). The seed also records Specification Index commodity and FX references. `trade_xyz_asset_checks` records actual Hyperliquid metadata availability and is required for live trade.xyz orders. `trade_xyz_kis_mappings` records which KIS quote route, if any, can provide reference market data for the same trade.xyz asset.

`kis_hl.cli` provides operational commands. Live orders require `--live`; dry-run is the default.

`docs/strategy_execution_design.md` records the strategy skill/tool integration and existing execution limits. Hermes loads `.agents/skills/trend-strategy/` for strategy judgment and owns timing/briefings/notification. `kis_hl.strategy_tools` supplies deterministic indicators, setup predicates, ATR stop proposals, risk-unit sizing and decision evidence through the existing CLI. Decisions reuse `strategy_signals`; protected execution and trailing remain in the existing supervisor rather than a new strategy daemon.

## Hyperliquid execution identity

`HyperliquidConfig.account_address` is always the effective execution account.
`master_account_address` retains the selected profile's wallet identity;
`subaccount_address` is an explicit optional route, never inferred from balances or
address inequality. Subaccount configurations validate both address formats,
reject self-targets, and enforce execution-account/target equality even through
`dataclasses.replace`.

The SDK receives the effective `account_address` **and** the subaccount as
`vault_address`: the latter participates in both signing and `/exchange` routing.
`account_address` alone does not route signed actions. `_load_sdk` rechecks public
`userRole` evidence on every subaccount use, including reuse of a cached SDK.
The derived signer must be the configured master; agent keys fail closed in this
initial implementation. Failed reads, unexpected roles, and mismatched masters
prevent SDK construction/action dispatch. Dry runs display identity but do not
validate exchange permissions.

Consumer audit: public default reads and SDK `user_state`, `execution_lock`,
`cli` trailing ownership, `trailing_runner` stored account/recovery checks,
`ManagedHyperliquidGateway` supervisor scope, and `operations_cli` journal and
capability scopes all consume the same effective `account_address`. No database
migration or reassignment of old master-scoped records occurs. Order request JSON
also retains routing identity. The sole account-changing `replace` path in
`scope_client` is a public-read override: it clears the private key, master and
subaccount route when selecting a different account, so the returned config cannot
be reused to sign under an unrelated scope. Other replacements do not change
Hyperliquid account identity.

## Data Flow

Interactive, code-grounded views generated from repository revision
`e012d2533463b6dd38abf32aee09e150719177f3`:

- [High-level system architecture](architecture/system-architecture.html)
- [Live order request sequence](architecture/live-order-sequence.html)
- [Market data, eligibility, and audit flow](architecture/market-data-flow.html)
- [Binance user data stream lifecycle](architecture/binance-user-stream-sequence.html)
- [Binance trading, market stream, and order event flow](architecture/binance-trading-data-flow.html) (order placement is shown as planned)
- [Binance order round trip](architecture/binance-order-roundtrip-sequence.html) (planned: guard, signed submit, fill confirmation over the user stream)

```mermaid
flowchart LR
  Env[".env"] --> Config["Config loader"]
  Config --> KIS["KIS REST client"]
  Config --> RefData["Reference data client"]
  Config --> HLInfo["Hyperliquid info client"]
  Config --> HLTrade["Hyperliquid SDK trading client"]
  KIS --> SQLite["SQLite storage"]
  RefData --> SQLite
  HLInfo --> CLI["CLI JSON output"]
  HLTrade --> SQLite
  CLI --> KISMap["trade.xyz KIS mapping"]
  KISMap --> KIS
  CLI --> RefMap["trade.xyz reference mapping"]
  RefMap --> RefData
  CLI --> XYZMarket["trade.xyz universe / funding / spread"]
  XYZMarket --> HLInfo
  CLI --> SQLite
```

## Safety Decisions

- Autonomous entry/add-up orchestration remains unimplemented; explicit enrolled-position trailing exits are supported.
- Signed Hyperliquid actions use the SDK rather than hand-written signatures.
- BTCUSDC futures signal evaluation is available through `btc-3h-breakout`; websocket-driven dry-run/live execution is available through `btc-3h-monitor`.
- `btc-3h-monitor` submits the requested entry size and stop from the signal price. It does not yet reconcile existing BTC positions or confirm actual average fill price before deriving the stop.
- Trade journal entries are explicit CLI records until order/fill reconciliation can create them automatically at position close.
- Normal live entries for trade.xyz assets should follow the relevant underlying market session documented in `docs/trading_hours.md`, not Hyperliquid's broader availability.
- Hyperliquid stop-loss trigger orders are reduce-only and require an explicit trigger price.
- The CLI stores raw order responses and protective-order rows so order IDs, statuses, trigger prices, and covered size remain auditable.
- Secrets are never logged intentionally and `.env` is ignored by git.
- Binance orders are dry-run by default; `--live` is explicit. Live placement requires `BINANCE_LIVE_SYMBOLS`, credentials, one-way position mode, and the shared account lock, and exchange rejections are recorded as `rejected` submissions rather than raised.
- Binance protective orders are exchange-side algo orders (`STOP_MARKET` closePosition, `TRAILING_STOP_MARKET` via `/fapi/v1/algoOrder`); the client-side trailing runner remains Hyperliquid-only.
- An ambiguous exchange outcome is stored as `unknown`, not `rejected`, so an operator or daemon cannot mistake a possibly-filled order for a failed one.

## Assumptions

- `.env` contains the correct key profile for the intended KIS and Hyperliquid environment.
- KIS sandbox mode is active unless `SANDBOX=false`.
- trade.xyz assets are available through Hyperliquid HIP-3 under the `xyz` dex namespace.
- BTC/USDC spot should use the Hyperliquid L1 name `UBTC/USDC` on mainnet.

## Open Risks

- The active trade.xyz asset list and session hours can change; validate metadata before live orders.
- KIS quote routing for NYSE Arca ETFs uses `AMS` and still needs live-account confirmation per ETF symbol.
- `XYZ100`, `SP500`, and `JP225` use KIS overseas index intraday chart data, not a dedicated current-price quote endpoint.
- Commodity KIS rows are reference-only until overseas futures front-contract resolution is implemented from KIS futures master data.
- Spot metals and FX rows are reference-only until exact KIS quote routes are confirmed; futures proxies are intentionally not enabled.
- Yahoo Finance data is useful as a secondary cross-check, but it can be rate-limited and does not provide an exchange-licensed production data guarantee.
- Hyperliquid funding and spread snapshots are stored for suitability review only. They are not yet wired into automatic entry rejection, position sizing changes, or liquidation-risk checks.
- Hyperliquid SDK behavior for spot market orders should be tested with a small live or testnet order before using spot market orders operationally.
- The trailing worker consumes Hyperliquid allMids through the maintained connection layer. Persistent raw tick tables and unified KIS/Hyperliquid strategy orchestration remain unimplemented.
- Binance `ALGO_UPDATE` user-stream events (conditional order lifecycle) are counted but not yet parsed into `order_events`; protective-order reconciliation currently relies on `binance-orders` (`open_algo_orders`).
- Binance order placement has been validated with unit tests and the exchange test endpoint, not with a live or demo fill; the first live order should be a minimum-size BTCUSDT order watched through `binance-user-stream`.
- The Binance user data stream parser follows the documented `ORDER_TRADE_UPDATE` schema and unit tests, but has not yet been exercised against a live or demo Binance session. Verify field names on the futures demo environment before relying on stored `order_events` for reconciliation.
- Binance futures websocket streams are partitioned by route: `/public` serves only the high-frequency `bookTicker`/`depth` streams and `/market` serves `markPrice`, `aggTrade`, `kline`, and the rest (verified live on 2026-09-16). One connection cannot mix the two, so `binance-stream` rejects a mixed request and the operator runs one process per route. The legacy unprefixed `/stream` root still answers but only delivers public-tier streams, which matches Binance's 2026-04-23 migration notice; URL overrides must use the routed roots. A threaded multi-route client is a possible follow-up.

## Trailing management components

- `kis_hl.trailing`: pure Decimal policy and conservative receive-time 9-minute bar
  aggregation. Frozen risk distance and monotonic H/T are separate from execution.
- `kis_hl.trailing_storage`: versioned SQLite position snapshots, atomic exit
  decisions, pre-send UNKNOWN attempts, and structured state-event history. All
  `trailing_*` tables are initialized on first trailing CLI use. Prices and sizes
  are decimal strings; active generations and exchange cloids are unique.
- `kis_hl.trailing_runner`: enrollment verification, REST account/order/fill
  reconciliation, bounded IOC exits, managed-stop cleanup, WebSocket supervision
  and offline replay. See the strategy document for the behavior contract.
- `kis_hl.execution_lock`: reentrant POSIX account lock shared by the worker and
  signed client operations. All local live commands must use the same database;
  another host or external trading app is outside this ownership boundary.
- `kis_hl.streaming`: optional idle/disconnect callbacks let the owner persist
  degraded/reconciling state even when the managed symbol is silent.

The Hyperliquid adapter adds frontend open orders, order status by oid/cloid,
non-aggregated fills by time, explicit cloid forwarding, cancel-by-oid, and bounded
perpetual exit rounding. It loads both base and xyz SDK metadata. Generic order
rejections are distinguished from submission; this does not imply filled quantity.
The worker's attempts retain raw exchange responses independently of manual
`order_submissions` / `protective_orders` rows. Auto-journal creation remains absent.

## Protected trading implementation

| Responsibility | Implemented module/state |
| --- | --- |
| Analysis versus execution identity | `instruments.py`; explicit broker/listing/currency/underlying catalog |
| Account capability evidence | `capabilities.py`; append-only `capability_evidence` scoped to instrument/account/order/session validity |
| Exact KIS routes | `kis/client.py`, `kis/routes.py`; full pagination, no automatic write retry |
| Order ownership and recovery | `managed_execution.py`; `managed_positions`, `managed_intents`, `managed_attempts`, `managed_events`, `managed_supervisors` |
| Actual venue snapshots | `managed_gateways.py`; entry/exit/readback semantics, ATR provenance, price freshness and exposure caps |
| Future skill output and authority | `strategy_signals.py`; immutable `strategy_versions`, `strategy_signals`, bounded `execution_grants` |
| Actual-history ingestion | `journal_history.py`; native HL fills/funding and unresolved KIS/spot snapshots |
| Journal reconciliation and schedule | `journal_sync.py`; `journal_source_fills`, `journal_cash_costs`, `journal_sync_runs`, `journal_cycles`, `journal_sync_schedule`, `journal_position_checks` |
| Harness-neutral commands | `operations_cli.py`, registered by the existing `cli.py` parser |

The target Archify views show the managed entry path, external HTS/web execution
path, deferred journals and future strategy/notification boundaries. The implemented
supervisor directly reuses the deterministic `Trail` policy rather than handing
partial entries to the older single-position enrollment runner. Journal derivation
and publication share one SQLite transaction, so no separate asynchronous outbox
consumer is needed for local publication. Notification transport and strategy-code
execution remain future extension points. All three diagrams remain target-design
views; they do not claim a notification service is deployed.

The [Hermes new-entry sequence](architecture/hermes-entry.html) documents the
current CLI-to-supervisor path, including queue ownership, partial-fill protection
and concurrent trailing. See the [operating steps](trading-operations.md#harness-originated-entry)
for live mode and worker lifetime.

SL and trailing provider decisions are independent. New Hyperliquid managed plans
default to native continuous-mark trailing with concurrent local nine-minute backup.
Local tracking can start with observed fills; native submission waits for terminal
entry and verified fixed-SL coverage. `hyperliquid/trailing.py` owns the observed wire/readback contract;
`managed_gateways.py` binds native order identity, and `managed_execution.py`
persists attempts and reconciles separate fixed-SL/trailing coverage. No additional
database schema or worker is introduced. Distance precision is validated and
persisted before entry, separately from the current market-price grid. Missing
native IDs or rejected submissions require intervention because the observed
trailing action has no client ID; this specific intervention retains fixed-SL
monitoring. Condition parsing failure on an otherwise verified owned trailing order
also preserves independent SL supervision with zero trailing coverage. Identity,
order semantics and account validation remain strict; generic intervention clears
the native-only exception. Valid same-ID readback can recover without resubmission.
Open waiting readback is distinct from active trailing coverage and
does not itself request an exit. Native KIS SL/trailing remain
unverified; local protection requires an active worker. Exact HTS equivalence is not
assumed. The account supervisor serializes actual attempts while its journal worker
has a separate account lock and a configurable 10800-second default interval.
Unknown/manual positions are not automatically adopted. Explicit `order adopt`
queues ADOPTING in SQLite. `manual_adoption.py` validates source entry/fills and
existing SL under the supervisor lock; atomic imported attempts bind ownership
without broker writes. The gateway uses the original fill-history window, while
admission time starts local tracking. Both trailing policies share one exit ledger;
reduce-only exits reconcile residuals before cleanup. Imported orders are excluded
from automatic agent-origin enrichment. See the [handoff diagram](architecture/manual-position-handoff.html)
and [operating contract](trading-operations.md#manual-position-handoff). Their source history still
belongs in the journal independently of live eligibility.

Storage migrations are additive. Source revisions and old statistics snapshots are
retained. Missing costs, opening inventory, chronology or retention evidence stay
pending; KIS cumulative order rows need statement supplementation. Same-account
currencies and strategy populations are reported separately. Operational contracts,
rollout limits, commands and rollback are in [trading operations](trading-operations.md).

## Unified trading data storage

`data_store.py` and `data_migrations.py` add a versioned canonical schema to the
same local SQLite path. Immutable compressed payloads and source observations
feed indexed fact revisions; account ingestion/import, market series, quality
selection, journals and analysis consume those facts. `analysis_inputs` pins
transitive dependencies. Jobs and report artifacts have separate operational
attempt/publication state. Existing managed/trailing/eligibility tables remain
unchanged. CLI registration lives in `data_cli.py`.

The [data-flow diagram](../reports/sdlc/unified-trading-data/design/dataflow.html)
and [logical specification](../specs/unified-trading-data.md) describe the broader
design. The first implementation uses validated dataset payloads in a shared
fact table rather than every proposed physical table. The actual supported
adapters, precision/coverage limits, rollout, persistence and maintenance commands
are documented in [unified data operations](unified-data-operations.md).
