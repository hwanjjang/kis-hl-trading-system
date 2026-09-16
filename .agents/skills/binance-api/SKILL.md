---
name: binance-api
description: Binance USDⓈ-M futures API reference for this repo. Use when adding or debugging a Binance REST/WebSocket call in kis_hl/binance, looking up a /fapi path, signing a request, handling listenKey or user-data-stream events, naming a market stream, checking BTCUSDT tick/lot/notional filters, or handling rate-limit (429/418) and error-code (-1xxx/-2xxx/-4xxx) responses.
---

# Binance USDⓈ-M Futures API

Use this skill for any work that touches Binance: `kis_hl/binance/client.py`,
`kis_hl/binance/ws.py`, `kis_hl/config.py` (`load_binance_config`), and the `binance-*`
CLI commands. Facts below were verified on 2026-09-16 against
`developers.binance.com` (USDⓈ-M futures docs) and live public endpoints.

## 0. Ground rules for this repo

- All REST calls go through `BinanceFuturesClient` (stdlib `urllib`, HMAC via stdlib
  `hmac`). Do not add `requests` or the `binance-futures-connector` SDK.
- Credentials come from `.env` via `load_binance_config()`. `BINANCE_KEY_PROFILE=production`
  selects `PRO_BINANCE_APIKEY`/`PRO_BINANCE_SECRET`. Never print or log the API key, the
  secret, or a `listenKey`. Tests compare emptiness, never values.
- Public reads need no key. Signed reads fail closed before any network call when the key
  or secret is empty. listenKey calls send only the `X-MBX-APIKEY` header.
- **This repo places no Binance orders yet.** Adding `POST /fapi/v1/order`, cancel, modify,
  leverage, or margin-type changes is a scope change under `AGENTS.md` trading safety: it
  needs a dry-run default, rejecting tests first, `--live` off by default, and demo-environment
  evidence before a live path.
- Never attach a Binance MCP server (official Agent OS MCP or community) or any
  order-capable vendor tool to an agent session with live keys. Same rule as KIS/Hyperliquid.
- Every new call needs a unit test in `tests/test_binance_client.py` or
  `tests/test_binance_ws.py` with a stubbed transport. Tests never hit the network.

## 1. Environments

| | Mainnet | Demo (testnet) |
|---|---|---|
| REST base | `https://fapi.binance.com` | `https://demo-fapi.binance.com` (legacy `https://testnet.binancefuture.com` still answers) |
| Market WS (markPrice, aggTrade, kline, …) | `wss://fstream.binance.com/market` | `wss://demo-fstream.binance.com/market` |
| Public WS (bookTicker, depth only) | `wss://fstream.binance.com/public` | `wss://demo-fstream.binance.com/public` |
| User WS | `wss://fstream.binance.com/private` | `wss://demo-fstream.binance.com/private` |
| Env keys | `BINANCE_BASE_URL`, `BINANCE_WS_MARKET_URL`, `BINANCE_WS_PUBLIC_URL`, `BINANCE_WS_USER_URL` | `BINANCE_TESTNET=true` selects the demo defaults |

**Routes are partitioned by stream tier** (verified live 2026-09-16): `/public` delivers
only `bookTicker`/`depth`; `/market` delivers `markPrice`, `aggTrade`, `kline`, and the
others; subscribing to the wrong tier yields a silent, empty stream. `stream_route()` and
`market_stream_url()` enforce one tier per connection. The legacy unprefixed `/stream`
root still answers but only carries public-tier streams (consistent with the
2026-04-23 migration notice); do not rely on it.

## 2. Request kinds

| Kind | Auth | Example |
|---|---|---|
| Public GET | none | `/fapi/v1/exchangeInfo`, `/fapi/v1/premiumIndex`, `/fapi/v1/ticker/bookTicker`, `/fapi/v1/klines`, `/fapi/v1/time` |
| Signed GET | `X-MBX-APIKEY` + `signature` | `/fapi/v2/account`, `/fapi/v2/positionRisk`, `/fapi/v1/openOrders`, `/fapi/v1/order` |
| API-key only | `X-MBX-APIKEY` | `POST/PUT/DELETE /fapi/v1/listenKey` |

Signing: append `recvWindow` (default 5000 ms) and `timestamp` (ms) to the query, compute
`HMAC-SHA256(secret, query_string)` as lowercase hex, append `&signature=<hex>`. The
signature must cover the exact byte string sent; `sign_query()` in `client.py` is the only
implementation. Ed25519/RSA keys are supported by Binance but not by this repo.

Full path table and response keys: `references/rest-endpoints.md`.

## 3. What this repo already wraps

`BinanceFuturesClient` (`kis_hl/binance/client.py`):

| Method | Path | Used by |
|---|---|---|
| `server_time()` | `GET /fapi/v1/time` | clock checks |
| `exchange_info(symbol=)` / `symbol_filters(symbol)` | `GET /fapi/v1/exchangeInfo` | `binance-info` |
| `premium_index(symbol)` | `GET /fapi/v1/premiumIndex` | `binance-mark` |
| `book_ticker(symbol)` | `GET /fapi/v1/ticker/bookTicker` | `binance-mark` |
| `klines(symbol, interval, limit=, start_time_ms=, end_time_ms=)` | `GET /fapi/v1/klines` | `binance-candles` |
| `account()` | `GET /fapi/v2/account` (signed) | account reads |
| `position_risk(symbol=)` | `GET /fapi/v2/positionRisk` (signed) | `binance-orders` |
| `open_orders(symbol=)` | `GET /fapi/v1/openOrders` (signed) | `binance-orders` |
| `order_status(symbol, order_id= / client_order_id=)` | `GET /fapi/v1/order` (signed) | reconciliation |
| `create_listen_key()` / `keepalive_listen_key()` / `close_listen_key()` | `/fapi/v1/listenKey` | `binance-user-stream` |

`kis_hl/binance/ws.py`: `mark_price_stream`, `book_ticker_stream`, `kline_stream`,
`agg_trade_stream`, `stream_route`, `market_stream_url`, `user_stream_url`, `BinanceMarketStreamClient`,
`BinanceUserStreamClient`, `parse_market_ticks`, `parse_order_event`, `order_event_to_row`.

Storage: market frames go to `market_ticks` with `source=binance`, `market=usdm_futures`;
order events go to `order_events` with `venue=binance`.

## 4. Symbol filters that reject after you send

Read them from `exchangeInfo`, never hardcode. BTCUSDT perpetual on 2026-09-16:

| Filter | Value | Consequence |
|---|---|---|
| `PRICE_FILTER.tickSize` | `0.10` | prices must be multiples of 0.1 (`pricePrecision` 2) |
| `LOT_SIZE.stepSize` / `minQty` | `0.001` / `0.001` | round quantity down to 3 decimals |
| `MARKET_LOT_SIZE.maxQty` | `120` | market orders larger than this are rejected |
| `MIN_NOTIONAL.notional` | `50` | quantity × price must be ≥ 50 USDT |
| `PERCENT_PRICE` | ±5% of mark | limit prices outside the band are rejected |
| `orderTypes` | LIMIT, MARKET, STOP, STOP_MARKET, TAKE_PROFIT, TAKE_PROFIT_MARKET, TRAILING_STOP_MARKET | server-side trailing stop exists (`callbackRate`, `activationPrice`) |
| `timeInForce` | GTC, IOC, FOK, GTX, GTD | GTX = post-only |

`symbol_filters()` returns these as Decimals under `tick_size`, `step_size`, `min_qty`,
`min_notional`, `price_precision`, `quantity_precision`, `order_types`, `time_in_force`.

Kline intervals: `1m 3m 5m 15m 30m 1h 2h 4h 6h 8h 12h 1d 3d 1w 1M`. There is **no `3h`**;
`klines()` and `kline_stream()` reject it. Aggregate `1h` bars for the 3H strategy.

## 5. Rate limits

- `REQUEST_WEIGHT` 2400 per minute per IP; `ORDERS` 300 per 10 s and 1200 per minute per
  account. Response header `x-mbx-used-weight-1m` is surfaced as `client.last_used_weight`.
- HTTP 429 = limit hit, back off. HTTP 418 = IP ban (2 minutes to 3 days). Never retry
  immediately on either.
- HTTP 503 with `"Unknown error"` means the request may have executed: verify via
  `order_status()` or the user stream before retrying. 503 `"Service Unavailable"` is a
  confirmed failure. Error `-1008` = server overload.
- WebSocket: one connection is valid 24 h; max 1024 streams per connection; max 10 inbound
  messages per second; the server pings every 3 minutes and closes after 10 minutes
  without a pong (`websocket-client` answers pings automatically).

Codes and messages: `references/limits-and-errors.md`.

## 6. WebSocket

- Market data: combined form `wss://.../market/stream?streams=btcusdt@markPrice@1s/btcusdt@aggTrade`
  (or `wss://.../public/stream?streams=btcusdt@bookTicker`) wraps frames as
  `{"stream": ..., "data": {...}}`. Stream names are lowercase symbols. One connection per
  route tier. This repo uses the URL form only, so a reconnect needs no subscription replay.
- User data: `POST /fapi/v1/listenKey` → connect `wss://.../private/ws/<listenKey>`.
  The key is valid 60 minutes; `PUT` extends it. `BinanceUserStreamClient` requests a fresh
  key on every (re)connect, renews every 30 minutes on idle ticks, and raises on
  `listenKeyExpired` so the maintained runner reconnects.
- Events: `ORDER_TRADE_UPDATE` (order/fill state), `ACCOUNT_UPDATE` (balances and
  positions), `MARGIN_CALL`, `listenKeyExpired`, `ALGO_UPDATE` (conditional orders).
  Field legend and stream payloads: `references/websocket.md`.

## 7. Adding a new REST call (checklist)

1. Confirm the path, weight, and whether it is signed in `references/rest-endpoints.md`
   or the official docs (`developers.binance.com/docs/derivatives/usds-margined-futures`).
2. Add a keyword-only method on `BinanceFuturesClient` that calls `self._request(...)`
   with `signed=True` or `api_key_header=True` as needed. Normalize numbers to `Decimal`.
3. Add a test in `tests/test_binance_client.py` using `RecordingClient` and assert the exact
   URL, query order, header, and signature.
4. If it changes stored data, update `kis_hl/storage.py`, `docs/architecture.md`, README.
5. Run `python3 -m unittest tests.test_binance_client tests.test_binance_ws tests.test_cli -q`.

Probe a public response shape (read-only): `scripts/fapi_get.sh /fapi/v1/premiumIndex symbol=BTCUSDT`.

## 8. Reference files

- `references/rest-endpoints.md` — public and signed paths, parameters, weights, response keys.
- `references/websocket.md` — stream names, payload keys, user-data events and field legend.
- `references/limits-and-errors.md` — rate limits, HTTP status semantics, error codes.
- `scripts/fapi_get.sh` — GET a public `/fapi` path for shape checking.

Official docs: https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info
Machine-readable index: https://developers.binance.com/en/docs/llms.txt
