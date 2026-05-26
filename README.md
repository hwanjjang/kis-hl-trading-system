# KIS Hyperliquid Trading System

This project collects market data through Korea Investment & Securities (KIS) Open API and submits guarded Hyperliquid orders for BTC/USDC and trade.xyz RWA assets.

The first implementation is intentionally small:

- KIS REST market data collection for domestic, overseas quote, and overseas daily chart endpoints.
- Hyperliquid public `info` calls for mids, books, and candles.
- Hyperliquid signed trading through the official `hyperliquid-python-sdk`.
- SQLite persistence for collected market payloads and order submissions.
- SQLite trade.xyz asset and KIS market-data mapping tables.
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
```

Hyperliquid uses wallet-based signing, not exchange API keys:

```bash
HYPERLIQUID_WALLETADDRESS=0x...
HYPERLIQUID_PRIVATEKEY=0x...
HYPERLIQUID_BASE_URL=https://api.hyperliquid.xyz
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
```

Fetch trade.xyz mids from the HIP-3 dex namespace:

```bash
python -m kis_hl.cli hl-mids --dex xyz --symbols XYZ100 SP500 SAMSUNG
```

Create or refresh the local trade.xyz asset mapping table:

```bash
python -m kis_hl.cli xyz-assets seed
python -m kis_hl.cli xyz-assets list --tradable-only
python -m kis_hl.cli xyz-assets verify --asset-class equity_index
```

Run `xyz-assets verify` against the same `--db` that live orders will use. The default live verification freshness window is 24 hours.

Create or refresh the trade.xyz to KIS quote mapping table, then fetch the mapped KIS quote:

```bash
python -m kis_hl.cli xyz-assets seed-kis
python -m kis_hl.cli xyz-assets kis-list --status active
python -m kis_hl.cli xyz-assets kis-fetch --symbol SAMSUNG --store
python -m kis_hl.cli xyz-assets kis-collect --symbols SAMSUNG KR200 SP500 --delay-ms 300
```

`kis-fetch` rejects excluded or unsupported mappings. `kis-collect` stores active mappings by default and continues after per-symbol failures unless `--fail-fast` is passed. `KR200` uses the KIS domestic index current-price endpoint. `XYZ100`, `SP500`, and `JP225` use the KIS overseas index intraday chart endpoint.

Prepare an order without sending it:

```bash
python -m kis_hl.cli trade --symbol BTCUSDC --side buy --order-type limit --size 0.001 --price 100000
```

Place a live order only after validating the resolved symbol, size, price, account, and network:

```bash
python -m kis_hl.cli trade --live --symbol xyz:XYZ100 --side buy --order-type limit --size 1 --price 1000
```

## Safety Notes

- Live trading is opt-in with `--live`.
- BTC/USDC resolves to Hyperliquid mainnet spot `UBTC/USDC` because Hyperliquid remaps the UI label. Live spot orders resolve that pair through `spotMeta` and submit the `@index` coin expected by HyperCore.
- trade.xyz assets should be passed as `xyz:ASSET` or with `--dex xyz`.
- Live trade.xyz orders are limited to assets marked tradable in the local mapping table.
- Live trade.xyz orders also require a recent successful `xyz-assets verify` check in SQLite.
- Non-IPO assets are excluded from the mapping by default.
- Stocks listed for less than 30 weeks are excluded from live trading.
- `KR200` replaces `EWY` for South Korea exposure; `JP225` replaces `EWJ` for Japan exposure.
- `xyz-assets kis-list` should be checked before relying on KIS data for a trade.xyz asset.
- Validate live metadata with `hl-mids --dex xyz` before trading a new RWA asset.
- Use an approved Hyperliquid API wallet per trading process to avoid nonce collisions.

## References

- `../ccxt-tradingview-webhook` for KIS TR IDs, token caching, and request throttling patterns.
- `../grid-bot-rotation-strategy` for official Hyperliquid Python SDK usage.
- Hyperliquid API docs for public info, signed exchange actions, asset IDs, tick/lot size, and API wallet rules.
- trade.xyz specification index for active RWA asset names and session constraints.
