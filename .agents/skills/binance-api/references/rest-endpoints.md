# Binance USDⓈ-M futures REST endpoints used or relevant to this repo

Base: `https://fapi.binance.com` (demo `https://demo-fapi.binance.com`). All responses are JSON.
Weights are per-IP `REQUEST_WEIGHT` units (2400/min).

## Public (no auth)

| Path | Params | Weight | Response keys |
|---|---|---|---|
| `GET /fapi/v1/ping` | – | 1 | `{}` |
| `GET /fapi/v1/time` | – | 1 | `serverTime` |
| `GET /fapi/v1/exchangeInfo` | `symbol` optional | 1 | `rateLimits[]`, `symbols[]` with `filters[]`, `orderTypes`, `timeInForce`, `pricePrecision`, `quantityPrecision`, `contractType`, `status` |
| `GET /fapi/v1/premiumIndex` | `symbol` | 1 | `markPrice`, `indexPrice`, `estimatedSettlePrice`, `lastFundingRate`, `interestRate`, `nextFundingTime`, `time` |
| `GET /fapi/v1/ticker/bookTicker` | `symbol` | 2 (1 per symbol) | `bidPrice`, `bidQty`, `askPrice`, `askQty`, `time`, `lastUpdateId` |
| `GET /fapi/v1/klines` | `symbol`, `interval`, `limit` (≤1500), `startTime`, `endTime` | 1–10 by limit | array rows: `[openTime, open, high, low, close, volume, closeTime, quoteVolume, trades, takerBuyBase, takerBuyQuote, ignore]` |
| `GET /fapi/v1/fundingRate` | `symbol`, `startTime`, `endTime`, `limit` | 1 | `fundingRate`, `fundingTime`, `markPrice` |
| `GET /fapi/v1/depth` | `symbol`, `limit` | 2–20 | `bids`, `asks`, `lastUpdateId` |

`normalize_kline()` maps a row to `t, o, h, l, c, v, T, quote_volume, trades` (Decimals), which
`kis_hl.signals._normalize_candle` accepts directly.

## Signed read-only (X-MBX-APIKEY + signature)

| Path | Params | Weight | Notes |
|---|---|---|---|
| `GET /fapi/v2/account` | – | 5 | balances, `positions[]`, `totalWalletBalance`, `availableBalance` |
| `GET /fapi/v2/positionRisk` | `symbol` optional | 5 | `positionAmt`, `entryPrice`, `markPrice`, `unRealizedProfit`, `liquidationPrice`, `leverage`, `marginType`; zero rows are returned too |
| `GET /fapi/v1/openOrders` | `symbol` optional | 1 with symbol, 40 without | open orders |
| `GET /fapi/v1/order` | `symbol` + `orderId` or `origClientOrderId` | 1 | `status`, `executedQty`, `avgPrice`, `type`, `reduceOnly`, `stopPrice` |
| `GET /fapi/v1/allOrders` | `symbol`, time range | 5 | history |
| `GET /fapi/v1/userTrades` | `symbol`, time range | 5 | fills |

Signed request assembly (this repo, `BinanceFuturesClient._request`):

```text
query = urlencode(params + recvWindow + timestamp)
signature = hex(HMAC_SHA256(secret, query))
GET {base}{path}?{query}&signature={signature}
X-MBX-APIKEY: {api_key}
```

`timestamp` must be within `recvWindow` of server time; error `-1021` means clock skew.

## listenKey (X-MBX-APIKEY only, no signature)

| Path | Effect |
|---|---|
| `POST /fapi/v1/listenKey` | returns `{"listenKey": "..."}`; valid 60 min; repeated POST returns the current key and extends it |
| `PUT /fapi/v1/listenKey` | extends validity 60 min |
| `DELETE /fapi/v1/listenKey` | closes the stream for the account |

## Order endpoints (NOT implemented; scope change under AGENTS.md)

`POST /fapi/v1/order` (`symbol`, `side`, `type`, `quantity`, `price`, `timeInForce`,
`reduceOnly`, `stopPrice`, `closePosition`, `workingType`, `callbackRate`, `activationPrice`,
`newClientOrderId`), `DELETE /fapi/v1/order`, `PUT /fapi/v1/order` (modify),
`POST /fapi/v1/leverage`, `POST /fapi/v1/marginType`. Any of these requires the safety
workflow in `SKILL.md` section 0 before use.
