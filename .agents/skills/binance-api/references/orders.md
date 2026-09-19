# Binance USDⓈ-M futures order endpoints (as used by `kis_hl/binance/trading.py`)

All signed: params + `recvWindow` + `timestamp` in the query string, HMAC-SHA256 `signature`,
`X-MBX-APIKEY` header. Orders count against the `ORDERS` limit (300 / 10 s, 1200 / min).

## `POST /fapi/v1/order` (and `POST /fapi/v1/order/test`) — regular orders only

| Param | Entry MARKET | Entry LIMIT |
|---|---|---|
| `symbol`, `side` | yes | yes |
| `type` | `MARKET` | `LIMIT` |
| `quantity` | yes | yes |
| `price` + `timeInForce` | – | yes (GTC/IOC/FOK/GTX) |
| `reduceOnly` | optional | optional |
| `newClientOrderId` | always set (`^[A-Za-z0-9._:/-]{1,36}$`) | same |
| `newOrderRespType` | `RESULT` | same |

`/order/test` takes the same parameters and returns `{}` without placing an order. Conditional
types on this endpoint return `-4120` since 2025-12-09.

## `POST /fapi/v1/algoOrder` — conditional orders (`algoType=CONDITIONAL`)

| Param | STOP_MARKET (closePosition) | STOP_MARKET (reduce-only) | TRAILING_STOP_MARKET |
|---|---|---|---|
| `algoType` | `CONDITIONAL` | `CONDITIONAL` | `CONDITIONAL` |
| `symbol`, `side`, `type` | yes | yes | yes |
| `quantity` | **no** | yes | yes |
| `triggerPrice` | yes | yes | – |
| `closePosition` | `true` | – | – |
| `reduceOnly` | **must not be sent** | `true` | `true` |
| `callbackRate` | – | – | 0.1–10 (percent) |
| `activatePrice` | – | – | optional; SELL above / BUY below current price |
| `workingType` | `MARK_PRICE` (this repo) | same | same (Binance default is `CONTRACT_PRICE`) |
| `clientAlgoId` | always set | same | same |
| `newOrderRespType` | `RESULT` | same | same |

Response: `algoId`, `clientAlgoId`, `algoType`, `orderType`, `symbol`, `side`, `positionSide`,
`quantity`, `algoStatus` (NEW, TRIGGERING, TRIGGERED, FINISHED, CANCELED, REJECTED, EXPIRED),
`triggerPrice`, `workingType`, `closePosition`, `reduceOnly`, `activatePrice`, `callbackRate`,
`createTime`, `updateTime`, `triggerTime`. Weight: 1 on the order-count limits, 0 on IP weight.
No test endpoint exists for algo orders.

Related: `GET /fapi/v1/algoOrder` (`algoId` or `clientAlgoId`), `GET /fapi/v1/algoOpenOrders`
(`symbol` required; the CLI queries every symbol with an order, a position, or in the live
allowlist), `DELETE /fapi/v1/algoOrder` (`algoId` or `clientAlgoId`; response `algoId`,
`clientAlgoId`, `code`, `msg`). The delete carries no symbol, so this repo looks the order up first
and refuses to cancel one whose symbol differs from the requested (allowlisted) symbol. The user stream reports these as `ALGO_UPDATE` events.

Response (RESULT): `orderId`, `clientOrderId`, `symbol`, `status` (NEW, PARTIALLY_FILLED, FILLED,
CANCELED, EXPIRED), `type`, `origType`, `side`, `positionSide`, `price`, `avgPrice`, `origQty`,
`executedQty`, `cumQuote`, `timeInForce`, `reduceOnly`, `closePosition`, `stopPrice`,
`workingType`, `priceProtect`, `activatePrice`, `priceRate`, `updateTime`.

A MARKET order's fill is only partially visible in the ack; treat `ORDER_TRADE_UPDATE` on the
user stream as the fill source of truth.

## `DELETE /fapi/v1/order`

`symbol` + `orderId` or `origClientOrderId`. Response mirrors the order object with
`status: CANCELED`. `-2011` means the order is already gone. Conditional orders are cancelled
through `DELETE /fapi/v1/algoOrder` instead.

## Outcome classification (this repo)

| HTTP / transport result | Submission status | Follow-up |
|---|---|---|
| 2xx | `submitted` | fills arrive on the user stream |
| 4xx with Binance code | `rejected` | fix the request; nothing was placed |
| 5xx, HTTP 408, code `-1007`, `Unknown error`, timeout after send | `unknown` → looked up once by `newClientOrderId` / `clientAlgoId`; found → `submitted` (`request.outcome = reconciled_after_unknown`) | if still `unknown`, query the order or watch the user stream before any retry |

## `GET /fapi/v1/positionSide/dual`

`{"dualSidePosition": false}` = one-way mode (required by this repo's live guard). Hedge mode
would require `positionSide` LONG/SHORT on every order; not supported here.

## Rejections to expect

| Code | Cause | Client-side prevention |
|---|---|---|
| -1111 | precision over `pricePrecision`/`quantityPrecision` | `round_to_step` |
| -4003 / -4004 | quantity below min / above max | `_round_quantity` |
| -4164 | notional below `MIN_NOTIONAL` | `_require_notional` |
| -2021 | stop would trigger immediately | `_require_stop_direction` |
| -2022 | reduce-only rejected (no position) | none; surfaces as `rejected` |
| -2019 | margin insufficient | none; surfaces as `rejected` |
| -4061 | order's position side does not match | hedge-mode guard |
| -4120 | conditional type sent to `/fapi/v1/order` | route to `/fapi/v1/algoOrder` |
