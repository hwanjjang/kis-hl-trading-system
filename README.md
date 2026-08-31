# KIS Hyperliquid Trading System

This project collects market data through Korea Investment & Securities (KIS) Open API and submits guarded Hyperliquid orders for BTC/USDC and trade.xyz RWA assets.

The first implementation is intentionally small:

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

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

The repository reads `.env` from the project root. Secrets must stay in `.env`; the file is ignored by git.
Use `.env.example` as the non-secret variable template.

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

The journal report includes average profit, average loss, success/failure ratio, win rate, adjusted success/failure ratio, max profit, max loss, average profit holding days, and average loss holding days.

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
- `../ccxt-tradingview-webhook` for KIS TR IDs, token caching, and request throttling patterns.
- `../grid-bot-rotation-strategy` for official Hyperliquid Python SDK usage.
- Hyperliquid API docs for public info, signed exchange actions, asset IDs, tick/lot size, and API wallet rules.
- trade.xyz specification index for active RWA asset names and session constraints.
