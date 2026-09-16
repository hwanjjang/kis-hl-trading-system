# Binance USDⓈ-M futures order endpoints (as used by `kis_hl/binance/trading.py`)

All signed: params + `recvWindow` + `timestamp` in the query string, HMAC-SHA256 `signature`,
`X-MBX-APIKEY` header. Orders count against the `ORDERS` limit (300 / 10 s, 1200 / min).

## `POST /fapi/v1/order` (and `POST /fapi/v1/order/test`)

| Param | Entry MARKET | Entry LIMIT | STOP_MARKET (closePosition) | STOP_MARKET (reduce-only) | TRAILING_STOP_MARKET |
|---|---|---|---|---|---|
| `symbol`, `side` | yes | yes | yes | yes | yes |
| `type` | `MARKET` | `LIMIT` | `STOP_MARKET` | `STOP_MARKET` | `TRAILING_STOP_MARKET` |
| `quantity` | yes | yes | **no** | yes | yes |
| `price` + `timeInForce` | – | yes (GTC/IOC/FOK/GTX) | – | – | – |
| `stopPrice` | – | – | yes | yes | – |
| `closePosition` | – | – | `true` | – | – |
| `reduceOnly` | optional | optional | **must not be sent** | `true` | `true` |
| `callbackRate` | – | – | – | – | 0.1–10 (percent) |
| `activationPrice` | – | – | – | – | optional (default: latest price) |
| `workingType` | – | – | `MARK_PRICE` default | same | same |
| `newClientOrderId` | always set (`^[A-Za-z0-9._:/-]{1,36}$`) | | | | |
| `newOrderRespType` | `RESULT` | | | | |

`/order/test` takes the same parameters and returns `{}` without placing an order.

Response (RESULT): `orderId`, `clientOrderId`, `symbol`, `status` (NEW, PARTIALLY_FILLED, FILLED,
CANCELED, EXPIRED), `type`, `origType`, `side`, `positionSide`, `price`, `avgPrice`, `origQty`,
`executedQty`, `cumQuote`, `timeInForce`, `reduceOnly`, `closePosition`, `stopPrice`,
`workingType`, `priceProtect`, `activatePrice`, `priceRate`, `updateTime`.

A MARKET order's fill is only partially visible in the ack; treat `ORDER_TRADE_UPDATE` on the
user stream as the fill source of truth.

## `DELETE /fapi/v1/order`

`symbol` + `orderId` or `origClientOrderId`. Response mirrors the order object with
`status: CANCELED`. `-2011` means the order is already gone.

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
