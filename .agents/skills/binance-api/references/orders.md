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

Response (RESULT): `orderId`, `clientOrderId`, `symbol`, `status` (NEW, PARTIALLY_FILLED, FILLED,
CANCELED, EXPIRED), `type`, `origType`, `side`, `positionSide`, `price`, `avgPrice`, `origQty`,
`executedQty`, `cumQuote`, `timeInForce`, `reduceOnly`, `closePosition`, `stopPrice`,
`workingType`, `priceProtect`, `activatePrice`, `priceRate`, `updateTime`.

A MARKET order's fill is only partially visible in the ack; treat `ORDER_TRADE_UPDATE` on the
user stream as the fill source of truth.

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

Related: `GET /fapi/v1/algoOrder` (`algoId` or `clientAlgoId`), `GET /fapi/v1/openAlgoOrders`
(`symbol` optional; the CLI falls back to per-symbol queries if the exchange answers -1102), `DELETE /fapi/v1/algoOrder` (`algoId` or `clientAlgoId`; response `algoId`,
`clientAlgoId`, `code`, `msg`). The delete carries no symbol, so this repo looks the order up first
and refuses to cancel one whose symbol differs from the requested (allowlisted) symbol. The user stream reports these as `ALGO_UPDATE` events.

## `DELETE /fapi/v1/order`

`symbol` + `orderId` or `origClientOrderId`. Response mirrors the order object with
`status: CANCELED`. `-2011` means the order is already gone. Conditional orders are cancelled
through `DELETE /fapi/v1/algoOrder` instead.

## Outcome classification (this repo)

| HTTP / transport result | Submission status | Follow-up |
|---|---|---|
| 2xx placement | `submitted`, or `rejected` for terminal/no-fill acknowledgements | partial fills remain submitted; inspect exchange status and fills |
| Definite 4xx rejection (excluding unknown-execution codes/messages below) | `rejected` | fix the request; nothing was placed |
| 5xx, HTTP 408, code `-1007` regardless of message, `Unknown error` or `status unknown` wording (including `-1000`/`-1006` responses), timeout after send | `unknown` → looked up once by client id or exchange id; a live order → `submitted` (`reconciled_after_unknown`), a terminal order with fills → `submitted` (`reconciled_partial_fill`), a terminal order without fills → `rejected` (`reconciled_terminal`), a confirmed cancel → `submitted` (`reconciled_cancel`) | if still `unknown`, query the order or watch the user stream before any retry |

## `GET /fapi/v1/positionSide/dual`

`{"dualSidePosition": false}` = one-way mode (required by this repo's live guard). Hedge mode
would require `positionSide` LONG/SHORT on every order; not supported here.

## Guard and recovery boundaries

Live placement requires the supported BTCUSDT symbol, configured allowlist, current COIN/PERPETUAL/TRADING metadata, credentials and one-way mode. Signed mutation holds the API-key-scoped lock. Live conditional placement also reads the current position inside that lock: side must close the position and explicit quantity must equal its absolute quantity. Other exchange clients can still change the position after this snapshot.

CLI commands send by default, with explicit `--dry-run` for local validation (public reads may occur). Direct Python methods keep `dry_run=True` as their default. Rejected/unknown CLI outcomes return 2/3. The exchange-test path is regular-order-only and does not place orders; successful exchange validation has not been observed in this environment.

Do not resubmit an unresolved order until its exchange state is established. Reusing a client ID is not durable idempotency: IDs can become reusable after the original order closes. There is no automatic replay of interrupted attempts or background reconciliation of unknown protection rows. `active` is an observed algo lifecycle state, not a remaining-coverage guarantee; TRIGGERED may refer to a working child order. Algo lookup retention can prevent cancellation of older orders, which remains fail closed.

Price tick/min/max and quantity/min-notional checks are local checks; dynamic price bands and exchange position/margin rules can still reject the request. Error codes are maintained in [limits-and-errors.md](limits-and-errors.md).

Official contracts checked 2026-09-24: [trade endpoints](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/trade), [general response semantics](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info), [error codes](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/error-code).
