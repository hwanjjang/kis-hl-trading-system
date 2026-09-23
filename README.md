# KIS Hyperliquid Trading System

This CLI system queries KIS and Hyperliquid, coordinates protected long entries, and maintains source-backed trade journals in SQLite. It supports KIS domestic/US ETFs and eligible Hyperliquid BTC/ETH and trade.xyz perpetuals.

Existing collection and trading tools include:

- KIS REST market data collection for domestic, overseas quote, and overseas daily chart endpoints.
- Hyperliquid public `info` calls for mids, books, and candles.
- Hyperliquid signed trading through the official `hyperliquid-python-sdk`.
- SQLite persistence for collected market payloads and order submissions.
- SQLite persistence for submitted reduce-only stop-market protective orders.
- SQLite trade.xyz asset, KIS market-data, and secondary reference-data mapping tables.
- SQLite trade.xyz universe, funding-rate, and top-of-book spread snapshots for suitability review.
- Strategy risk helpers for operating capital, ATR(10D), 30-week EMA, and position sizing.
- A live-order session guard that blocks non-reduce-only trade.xyz orders outside the mapped underlying market session unless explicitly overridden.
- CLI defaults that never place a live order unless `--live` is passed.
- Explicitly enrolled long-position trailing management, durable reconciliation, and offline tick replay.

## Multi-venue protected trading

```bash
python -m kis_hl.cli instrument list
python -m kis_hl.cli instrument verify --instrument kis:DRAM
python -m kis_hl.cli chart --instrument index:KOSPI --date-from 20260101 --date-to 20260911
python -m kis_hl.cli account positions --venue kis --market overseas
python -m kis_hl.cli order preview --input my-plan.json
python -m kis_hl.cli journal configure --venue kis --interval-seconds 10800
python -m kis_hl.cli journal status --venue kis
```

[Trading operations](docs/trading-operations.md) documents required plan fields,
protected entry/supervisor controls, actual-history journals, statement imports,
and future strategy-signal grants. Journal synchronization defaults to **3 hours**
and is configurable; protection runs separately. KIS order summaries remain pending
until exact execution/cost statements are supplied. Native KIS protection is not
inferred from stop-limit names. Notification delivery is not implemented.

New Hyperliquid managed plans default to native continuous-mark trailing plus
concurrent local nine-minute backup (`local_trailing_backup: true`). KIS stays local;
existing stored positions retain their policy. Read the
[protection contract and rollout limits](docs/trading-operations.md#protection-and-controls)
for provider selection and coordinated exit behavior.

For a manually entered protected HL long, use the [agent handoff workflow](docs/trading-operations.md#manual-position-handoff)
and [interactive diagram](docs/architecture/manual-position-handoff.html).
`order adopt` queues ownership verification without opening another position.

Explore the [architecture](docs/architecture/multi-venue-trading.html),
[protected-trade workflow](docs/architecture/protected-trade.html), and
[signals/journal flow](docs/architecture/signals-and-journal.html).
These target-design views include explicitly future components; see the
[implementation mapping](docs/architecture.md#protected-trading-implementation).

## Trailing stop management

Start with a network-free paper replay:

```bash
python -m kis_hl.cli --db /tmp/trailing-paper.sqlite trailing replay --input examples/trailing-stop-replay.jsonl
python -m kis_hl.cli --db /tmp/trailing-paper.sqlite trailing status
```

The example raises the threshold from 96 to 104 and records `PAPER_EXIT`; it does
not assume a fill price or profitability. Replay accepts JSONL: a `position`
header (`symbol`, `size`, `entry`, `atr`, `multiple`, `opened_ms`, `max_gap_ms`),
then `{ "time_ms": 123, "price": "100", "age_ms": 0 }` ticks or
`{ "type": "disconnect" }`. Each replay has a separate paper identity.

To shadow an existing protected long, supply its actual entry and native stop
order IDs (replace 123 and 456):

```bash
python -m kis_hl.cli --db data/kis_hl.sqlite trailing enroll --symbol BTC-PERP --entry-order-id 123 --stop-order-id 456 --multiple 2 --max-gap-ms 15000 --slippage 0.01
python -m kis_hl.cli --db data/kis_hl.sqlite trailing run --position-id POSITION_ID
python -m kis_hl.cli --db data/kis_hl.sqlite trailing status --position-id POSITION_ID
```

Enrollment reads account/order/fill/metadata data and 11 closed Hyperliquid daily
bars. It requires a fully filled single long entry, unchanged position quantity,
no unowned open orders in that coin, and a matching reduce-only Stop Market order
at or above the initial ATR risk floor. It creates no entry or SL. Paper enrollment
and execution are the defaults; paper exits record intent without sending or
simulating fills. Its ATR is frozen **at explicit enrollment**, and historical
pre-enrollment highs are not inferred. Enroll promptly after confirming protection.

Live management requires `--live` on both **enroll** and **run**. Modes cannot be
promoted in place. With live enabled, the worker can send only reduce-only exits
and cancel its enrolled stop after flatness is confirmed. It uses the supplied
slippage tolerance, at most 3 attempts within 120 seconds, and never resends an
ambiguous attempt without terminal evidence. All existing eligibility, credential
and metadata-freshness guards still apply; a blocked exit requires operator action.

Use the same `--db` for all live commands for an account. A POSIX account lock
allows one local worker and serializes signed actions; multi-host execution is
unsupported. Non-reduce-only entries in an enrolled coin are blocked until cleanup.
Do not run independent/manual strategies in that coin. Manual partial reductions
are reconciled; additions, reversals or unowned orders halt management.

`run --recover` explicitly rechecks a `MANUAL_INTERVENTION` state after the operator
has resolved its cause. It does not reset attempt counts, deadlines or adopt a new
stop/position. The fixed native SL stays in place during disconnects and exits.
Stopping the worker (including Ctrl-C or `--max-messages`) suspends trailing; it
never cancels that protection. `--max-reconnects` can bound reconnection attempts.

No live exchange execution has been verified for this feature. Mid-price signals
can differ from native mark-price triggers; gaps, IOC residuals and outages can
lose the latest trailing profit floor. Status shows verified coverage timestamps,
state/reason, exit intent and attempts. See
[the strategy design](docs/strategy_execution_design.md#implemented-trailing-management)
for exact scope, recovery and limitations.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

The repository reads `.env` from the project root. Secrets must stay in `.env`; the file is ignored by git.
Use `.env.example` as the non-secret variable template.
Paseo worktree workspaces copy `.env` from the source checkout automatically via the
`worktree.setup` hook in `paseo.json`; the hook is read from the committed base branch.

## Environment

KIS uses the same variable names as the reference project:

```bash
SANDBOX=true
KIS_API_ST_KEY=...
KIS_API_ST_SECRET=...
KIS_ST_STOCK_ACCOUNT=0000000000
KIS_API_KEY=...
KIS_API_SECRET=...
KIS_STOCK_ACCOUNT=0000000000
KIS_HTSID=...
KIS_WS_ST_URL=ws://ops.koreainvestment.com:31000
KIS_WS_URL=ws://ops.koreainvestment.com:21000
```

Hyperliquid uses wallet-based signing, not exchange API keys:

```bash
HYPERLIQUID_WALLETADDRESS=0x...
HYPERLIQUID_PRIVATEKEY=0x...
HYPERLIQUID_BASE_URL=https://api.hyperliquid.xyz
HYPERLIQUID_WS_URL=wss://api.hyperliquid.xyz/ws
```

Set `HYPERLIQUID_KEY_PROFILE=production` to use `PRO_HYPERLIQUID_WALLETADDRESS` and `PRO_HYPERLIQUID_PRIVATEKEY`.

## Commands

Verify the configured KIS account and read its domestic balance summary:

```bash
python -m kis_hl.cli kis-account
```

`SANDBOX=true` selects paper credentials; `SANDBOX=false` selects live credentials.
This read-only command prints a masked account number, environment and three KRW
amounts: `dnca_tot_amt` (deposit), `tot_evlu_amt` (total valuation), and
`scts_evlu_amt` (securities valuation). It does not list holdings or overseas/FX
details, place orders, or store balances. Failed or malformed responses exit with
status 1 and a generic error without raw vendor data. Account-check tokens are
cached in a credential-derived subdirectory of `KIS_TOKEN_DIR` to avoid reusing a
previous account's token; other commands retain their existing cache behavior.

Fetch a KIS overseas quote and persist the raw payload:

```bash
python -m kis_hl.cli kis-price --market overseas --exchange-code NAS --symbol AAPL --store
```

Fetch Hyperliquid mids for default HyperCore plus spot markets:

```bash
python -m kis_hl.cli hl-mids --symbols BTCUSDC
python -m kis_hl.cli hl-mids --symbols BTCUSDC-PERP
```

Fetch trade.xyz mids from the HIP-3 dex namespace:

```bash
python -m kis_hl.cli hl-mids --dex xyz --symbols XYZ100 SP500 SAMSUNG
```

Fetch public asset/account state for `HYPERLIQUID_WALLETADDRESS` without using the private key:

```bash
python -m kis_hl.cli hl-account
python -m kis_hl.cli hl-account --dex xyz
```

Create or refresh the local trade.xyz asset mapping table:

```bash
python -m kis_hl.cli xyz-assets seed
python -m kis_hl.cli xyz-assets list --tradable-only
python -m kis_hl.cli xyz-assets verify --asset-class equity_index
python -m kis_hl.cli xyz-assets verify --asset-class commodity
```

Run `xyz-assets verify` against the same `--db` that live orders will use. The default live verification freshness window is 24 hours.

Snapshot the live Hyperliquid `xyz` universe, funding history, and top-of-book spreads:

```bash
python -m kis_hl.cli xyz-assets universe-collect
python -m kis_hl.cli xyz-assets funding-collect --lookback-hours 24 --delay-ms 300
python -m kis_hl.cli xyz-assets spread-collect --delay-ms 300
python -m kis_hl.cli xyz-assets funding-collect --symbols SP500 XYZ100 GOLD DRAM KR200 EWY TSM LLY --lookback-hours 168
python -m kis_hl.cli xyz-assets spread-collect --symbols SP500 XYZ100 GOLD DRAM KR200 EWY TSM LLY
```

`universe-collect` stores the current Hyperliquid `xyz` market list and reports symbols that are new versus the previous snapshot or the curated seed on the first run. Each universe asset row stores Hyperliquid 24h base volume, 24h notional volume, and open interest when the API provides them. `funding-collect` stores idempotent hourly funding rows in `market_funding_rates`. `spread-collect` stores best bid, best ask, mid price, absolute spread, and spread bps in `market_spread_snapshots`.

Create or refresh the trade.xyz to KIS quote mapping table, then fetch the mapped KIS quote:

```bash
python -m kis_hl.cli xyz-assets seed-kis
python -m kis_hl.cli xyz-assets kis-list --status active
python -m kis_hl.cli xyz-assets kis-fetch --symbol SAMSUNG --store
python -m kis_hl.cli xyz-assets kis-collect --symbols SAMSUNG KR200 SP500 --delay-ms 300
```

`kis-fetch` rejects excluded or unsupported mappings. `kis-collect` stores active mappings by default and continues after per-symbol failures unless `--fail-fast` is passed. `KR200` uses the KIS domestic index current-price endpoint. `XYZ100`, `SP500`, and `JP225` use the KIS overseas index intraday chart endpoint. Commodity and FX rows keep their trade.xyz reference symbols in `trade_xyz_kis_mappings`, but remain `unsupported` until exact KIS collection routes are implemented.

Create or refresh secondary reference-data mappings, then collect Yahoo Finance chart quotes:

```bash
python -m kis_hl.cli xyz-assets seed-ref
python -m kis_hl.cli xyz-assets ref-list --asset-class commodity
python -m kis_hl.cli xyz-assets ref-fetch --symbol WTIOIL --store
python -m kis_hl.cli xyz-assets ref-collect --asset-class fx --delay-ms 300
```

Reference-data commands currently use Yahoo Finance chart data through the `yahoo_finance` provider. They are useful for comparing trade.xyz mids against commodity, FX, and index references when KIS is unavailable, but they are not a replacement for exchange-licensed production market data.

Collect 365 calendar days of daily OHLCV bars for tradable trade.xyz assets:

```bash
python -m kis_hl.cli xyz-assets daily-collect --days 365 --delay-ms 300
python -m kis_hl.cli xyz-assets daily-collect --asset-class commodity --days 365
python -m kis_hl.cli xyz-assets daily-collect --symbols WTIOIL AAPL --days 365
```

Daily collection stores idempotent rows in `market_daily_bars`. Commodity, FX, and index assets use the secondary Yahoo reference mapping; stock and ETF assets use their exchange ticker from `trade_xyz_assets`.

Suggested daily market-data refresh sequence:

```bash
python -m kis_hl.cli xyz-assets universe-collect
python -m kis_hl.cli xyz-assets verify
python -m kis_hl.cli xyz-assets funding-collect --lookback-hours 24 --delay-ms 300
python -m kis_hl.cli xyz-assets spread-collect --delay-ms 300
python -m kis_hl.cli xyz-assets daily-collect --days 365 --delay-ms 300
```

The daily sequence keeps new trade.xyz listings visible, refreshes live metadata verification, updates recent funding cost, records current liquidity/spread, and refreshes the daily bar history used by ATR and 30-week EMA checks.

Evaluate the BTCUSDC futures 3-hour close breakout signal:

```bash
python -m kis_hl.cli btc-3h-breakout --start-ms 1767139200000 --end-ms 1767258000000
```

The signal uses closed 3H Hyperliquid BTC perp candles. It returns `should_enter=true` only when the latest closed candle's close is above the previous candle high by default. Use `--lookback-candles` to compare against the highest high across more prior candles.

Monitor BTC spot websocket mids and prepare a BTC perp long entry when the closed 3H spot candle breaks the previous high:

```bash
python -m kis_hl.cli btc-3h-monitor --atr-10d 500
```

`btc-3h-monitor` is dry-run by default. It uses `80 USDC` entry notional and a stop-loss distance of `ATR(10D) * 2`, then prepares a BTC perp market buy and a reduce-only stop-market sell. If `--atr-10d` is omitted, the command fetches Hyperliquid BTC perp `1d` candles and calculates ATR(10D). Pass `--live` only after confirming account state, current position, ATR freshness, and order size.

Record a completed trade journal entry and include the required statistics snapshot:

```bash
python -m kis_hl.cli journal add \
  --symbol xyz:SP500 \
  --strategy breakout \
  --side long \
  --opened-at-ms 1780000000000 \
  --closed-at-ms 1780086400000 \
  --entry-price 7500 \
  --exit-price 7580 \
  --quantity 0.1 \
  --fees 0
python -m kis_hl.cli journal stats
```

The journal report calculates the nine review statistics from completed-position net return percentages. `success_failure_ratio` is average positive return divided by the absolute average negative return; `adjusted_success_failure_ratio` also weights those averages by win and loss frequency. Breakevens remain in the trade count but are excluded from the win-rate and ratio denominators. See `.agents/skills/trade-journal/` for the record boundary, formulas, holding-day convention, and edge cases.

Prepare an order without sending it:

```bash
python -m kis_hl.cli trade --symbol BTCUSDC --side buy --order-type limit --size 0.001 --price 100000
```

Prepare a reduce-only Hyperliquid stop-loss trigger order without sending it:

```bash
python -m kis_hl.cli trade --symbol xyz:XYZ100 --side sell --order-type stop-market --size 1 --trigger-price 950 --reduce-only
```

Place a live order only after validating the resolved symbol, size, price, account, and network:

```bash
python -m kis_hl.cli trade --live --symbol xyz:XYZ100 --side buy --order-type limit --size 1 --price 1000
```

Live non-reduce-only trade.xyz orders are rejected outside the mapped underlying market session by default. Use `--allow-outside-session` only for an explicitly reviewed special case. Reduce-only exits and stop-loss orders bypass the entry-session guard.

## Safety Notes

- Live trading is opt-in with `--live`.
- BTC/USDC resolves to Hyperliquid mainnet spot `UBTC/USDC` because Hyperliquid remaps the UI label. Live spot orders resolve that pair through `spotMeta` and submit the `@index` coin expected by HyperCore.
- BTCUSDC futures should be passed as `BTCUSDC-PERP`, `BTC-PERP`, or `BTCPERP`; these resolve to Hyperliquid's `BTC` perp coin.
- The BTCUSDC futures 3H breakout rule is implemented as signal evaluation only. It does not place a live order by itself.
- `btc-3h-monitor` is the first spot-websocket-to-perp execution path. It still relies on process-local duplicate-entry prevention and does not yet reconcile existing BTC positions before a live order.
- Completed trades should be recorded through `journal add` until fill reconciliation can write journal entries automatically.
- trade.xyz assets should be passed as `xyz:ASSET` or with `--dex xyz`.
- Live trade.xyz orders are limited to assets marked tradable in the local mapping table.
- Live trade.xyz orders also require a recent successful `xyz-assets verify` check in SQLite.
- Hyperliquid stop-loss trigger orders use `--order-type stop-market`, require `--trigger-price`, and require `--reduce-only`.
- Submitted reduce-only stop-market orders are recorded in `protective_orders` with trigger price, covered size, request ID, source order submission, and extracted Hyperliquid order ID when present.
- Funding and spread snapshots are stored for suitability review. They do not yet block live entries automatically.
- Operating capital is calculated as `floor(portfolio_value_usdc / 1000) * 1000 * 20`. Position sizing uses `ATR(10D) * N` as the stop distance and `1%` of operating capital as per-tranche risk.
- Non-IPO assets are excluded from the mapping by default.
- Stocks listed for less than 30 weeks are excluded from live trading.
- `KR200` replaces `EWY` for South Korea exposure; `JP225` replaces `EWJ` for Japan exposure.
- `WTIOIL` resolves to the Hyperliquid `xyz:CL` market because trade.xyz labels the contract WTIOIL while Hyperliquid exposes the CL key.
- Normal live entries should follow the underlying market's regular session, not Hyperliquid's broader 24/5 or 24/7 availability. See `docs/trading_hours.md`.
- Strategy sizing, ATR stops, add-up flow, and websocket execution behavior are documented in `docs/strategy_execution_design.md`.
- Commodity and FX KIS mappings are reference-only for now; do not rely on KIS collection for those assets until their rows become `active`.
- Yahoo Finance reference mappings are secondary checks and can be rate-limited or change ticker roll behavior without notice.
- `xyz-assets kis-list` should be checked before relying on KIS data for a trade.xyz asset.
- Validate live metadata with `hl-mids --dex xyz` before trading a new RWA asset.
- Check `xyz-assets universe-collect` for newly listed `xyz` markets before expanding the curated eligibility table.
- Review recent funding and spread data before opening or adding to a trade.xyz position, especially for single-name stocks and newly added markets.
- Use an approved Hyperliquid API wallet per trading process to avoid nonce collisions.

## References

- `AGENTS.md` holds the shared agent rules, and `CLAUDE.md` is the Claude Code entry point with the file-ownership table used to keep documentation single-sourced.
- `.agents/skills/kis-open-api/` (also linked as `.claude/skills/kis-open-api/`) is the KIS Open API skill for Claude Code and Codex: auth/transport rules, endpoint and TR ID tables, websocket protocol, and a search script over the official `koreainvestment/open-trading-api` samples.
- `.agents/skills/hyperliquid-api/` (also linked as `.claude/skills/hyperliquid-api/`) owns Hyperliquid REST/WebSocket, symbol, sizing, rate-limit, and rejection rules used by this repo.
- `.agents/skills/trade-journal/` (also linked as `.claude/skills/trade-journal/`) owns the completed-trade record contract and the nine Minervini-style review-statistics formulas.
- `../ccxt-tradingview-webhook` for KIS TR IDs, token caching, and request throttling patterns.
- `../grid-bot-rotation-strategy` for official Hyperliquid Python SDK usage.
- Hyperliquid API docs for public info, signed exchange actions, asset IDs, tick/lot size, and API wallet rules.
- trade.xyz specification index for active RWA asset names and session constraints.

Trailing IOC attempts carry a signed `expiresAfter` equal to the source price receive time plus its configured freshness budget. Local age checks include all reconciliation work; the exchange expiry also bounds delayed delivery. An expiry rejection consumes the existing bounded retry budget.

### Canonical trading and market data

The unified store preserves raw evidence, corrected fact revisions, separate
KIS/tradefi journals and reproducible analysis in `data/kis_hl.sqlite`.

```bash
python3 -m kis_hl.cli data migrate --apply
python3 -m kis_hl.cli data status
python3 -m kis_hl.cli market backfill --instrument kis:069500 --timeframe 1w --years 10
python3 -m kis_hl.cli market backfill --instrument hl:BTC --timeframe 1m
python3 -m kis_hl.cli data journal --accounts ACCOUNT_ID
```

See [unified data operations](docs/unified-data-operations.md) for manifest import,
bounded independent-statement reconciliation (`data reconcile`),
cost/funding rules, market coverage, jobs (account default: 10800 seconds),
exports, analysis and backup/restore. Weekly history targets ten calendar years;
actual provider/listing coverage may be shorter. Jobs require a running collector.

### Review account changes before applying them

Use `data audit-collect` with an explicit KIS or Hyperliquid account and time range
to capture private source evidence without changing the operational database.
`data audit-compare` writes the differences; `data audit-apply` requires the reviewed
report SHA-256 and explicit approval of corrections. Add `--journals` to regenerate
selected account journals and their combined report while preserving old reports.
See [the account audit workflow](docs/unified-data-operations.md#account-audit-and-explicit-adjustment)
for command examples, coverage limits and the offline smoke scenario.
