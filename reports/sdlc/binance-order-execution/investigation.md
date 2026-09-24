# Investigation — binance-order-execution (2026-09-16)

Question: how does the repo shape a guarded trading client, and what does Binance need for entry, stop, trailing, and cancel orders?

Verified repo facts (read by an Explore subagent, line refs in its report):
- `HyperliquidTradingClient.place_order` guard order: pure validation → build request (with `client_request_id`) → dry-run return before any allowlist/credential/network work → allowlist → verification → credentials → managed-position/session → SDK. `cancel_order` follows the same dry-run-first shape. `OrderSubmission(status, dry_run, resolved, request, response)`.
- `kis_hl/execution_lock.py`: `account_lock(network, account)` (sha256 key, POSIX flock in tmp) and `serialized_action` (reads `dry_run` kwarg; expects `config.account_address`). `BinanceConfig` has no `account_address`, so the Binance client must call `account_lock` explicitly.
- `storage.store_order_submission(...)` and `store_protective_order(...)` signatures; `protective_orders` columns; no `list_order_submissions` helper exists.
- CLI `trade`: `--live` store_true → `dry_run=not args.live`; stores submission then protective row when stop-market + reduce-only; `active = not dry_run and status == "submitted"`.
- `BinanceFuturesClient._request` is method-agnostic and puts all params (and the signature) in the query string; POST/DELETE need no transport change.
- No tick/step rounding helper exists in the repo; `normalize_symbol_filters` already yields Decimal `tick_size`, `step_size`, `min_qty`, `max_qty`, `market_max_qty`, `min_notional`.

Vendor facts (long-standing Binance USDⓈ-M contract; live public probe of exchangeInfo on 2026-09-16 for filters and order types):
- `POST /fapi/v1/order` params: `symbol`, `side`, `type`, `quantity`, `price` + `timeInForce` (LIMIT), `reduceOnly`, `stopPrice` (STOP_MARKET), `closePosition` (STOP_MARKET/TAKE_PROFIT_MARKET, no quantity, cannot combine with reduceOnly), `callbackRate` 0.1–10 and optional `activationPrice` (TRAILING_STOP_MARKET), `workingType` MARK_PRICE|CONTRACT_PRICE, `newClientOrderId`, `newOrderRespType` ACK|RESULT. Response includes `orderId`, `clientOrderId`, `status`, `type`, `origQty`, `executedQty`, `avgPrice`, `stopPrice`, `reduceOnly`, `closePosition`, `updateTime`.
- `POST /fapi/v1/order/test`: same params, validates without placing (returns `{}` on success).
- `DELETE /fapi/v1/order`: `symbol` + `orderId` or `origClientOrderId`.
- `GET /fapi/v1/positionSide/dual` → `{"dualSidePosition": bool}`; one-way mode is `false`.
- Common rejections: -2021 order would immediately trigger; -4164 notional below MIN_NOTIONAL; -1111 precision; -2022 reduce-only rejected; -4003/-4004 quantity bounds.

Unknowns: demo keys are not present, so a demo fill cannot be recorded in this task; the exchange test endpoint with real keys is the strongest safe smoke available.

Implication: implement `kis_hl/binance/trading.py` with `BinanceTradingClient(BinanceFuturesClient)` mirroring the Hyperliquid guard order, explicit `account_lock`, and Decimal rounding helpers; wire three CLI commands; reuse existing storage helpers.
