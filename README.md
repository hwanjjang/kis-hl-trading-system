# KIS Hyperliquid Trading System

This project collects market data through Korea Investment & Securities (KIS) Open API and submits guarded Hyperliquid orders for BTC/USDC and trade.xyz RWA assets.

The first implementation is intentionally small:

- KIS REST market data collection for domestic, overseas quote, and overseas daily chart endpoints.
- Hyperliquid public `info` calls for mids, books, and candles.
- Hyperliquid signed trading through the official `hyperliquid-python-sdk`.
- SQLite persistence for collected market payloads and order submissions.
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
- Validate live metadata with `hl-mids --dex xyz` before trading a new RWA asset.
- Use an approved Hyperliquid API wallet per trading process to avoid nonce collisions.

## References

- `../ccxt-tradingview-webhook` for KIS TR IDs, token caching, and request throttling patterns.
- `../grid-bot-rotation-strategy` for official Hyperliquid Python SDK usage.
- Hyperliquid API docs for public info, signed exchange actions, asset IDs, tick/lot size, and API wallet rules.
- trade.xyz specification index for active RWA asset names and session constraints.
