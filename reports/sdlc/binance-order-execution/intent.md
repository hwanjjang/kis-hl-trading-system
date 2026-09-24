# Intent — binance-order-execution (r1, 2026-09-16)

Problem: the Binance data plane (PR #17) reads market data and order events but cannot trade. AK wants to trade BTC on Binance USDⓈ-M futures with server-side stops.

Outcome: `BinanceFuturesClient` gains guarded, dry-run-by-default order placement (MARKET/LIMIT entry, STOP_MARKET close-position stop, TRAILING_STOP_MARKET), cancel, and exchange-side test validation; CLI commands expose them with explicit `--live`; submissions and protective orders are audited in SQLite; docs, skill, and diagrams reflect the implemented flow.

Acceptance criteria:
- AC1 `place_order`: MARKET or LIMIT entry with quantity rounded down to `stepSize`, price rounded to `tickSize`, `minQty` and `MIN_NOTIONAL` enforced (using price, or mark price for MARKET), `newClientOrderId` always set; dry-run (default) returns the prepared request without any network call; live sends a signed `POST /fapi/v1/order` and returns the acknowledgement.
- AC2 `place_stop_market`: `STOP_MARKET` with `closePosition=true` (no quantity, `workingType=MARK_PRICE` default) or `reduceOnly=true` with quantity; stop price rounded to tick; direction validated against side (SELL stop must be below mark for a long, BUY stop above mark for a short).
- AC3 `place_trailing_stop`: `TRAILING_STOP_MARKET` with `callbackRate` in [0.1, 10] (one decimal), optional `activationPrice` rounded to tick, `reduceOnly=true`, quantity rounded to step.
- AC4 `cancel_order`: signed `DELETE /fapi/v1/order` by `orderId` or `origClientOrderId`; dry-run default.
- AC5 `test_order`: signed `POST /fapi/v1/order/test` for exchange-side validation without placement; CLI `--exchange-test` uses it.
- AC6 Guards (fail closed): live requires credentials; live symbol must be in `BINANCE_LIVE_SYMBOLS` (default `BTCUSDT`); live rejects hedge (dual-side) position mode read from `GET /fapi/v1/positionSide/dual`; signed order actions run under the shared execution lock; filters are read from `exchangeInfo`, never hardcoded.
- AC7 CLI: `binance-trade` (entry), `binance-stop` (`--kind stop-market|trailing`), `binance-cancel`; all default to dry-run, `--live` explicit, `--no-store` opt-out; entries stored in `order_submissions` (venue `binance`), stops in `protective_orders`; output contains no credentials.
- AC8 Config `BINANCE_KEY_PROFILE=demo` selects `DEMO_BINANCE_APIKEY/SECRET` and the demo URLs; docs (README, architecture, skill tables, `.env.example`) and the order round-trip diagram updated to the implemented flow; full unittest suite green without network.

Out of scope: leverage/margin changes, hedge mode, strategy daemon wiring, unit sizing (#15), spot, order modification.
Constraints: stdlib urllib/hmac; dry-run default; agent never executes `--live`; secrets never printed; English artifacts.
Assumptions: one-way position mode on the account; demo keys, if AK provides them, go into `DEMO_BINANCE_*`.
Risks: order endpoint parameter set verified from long-standing Binance docs knowledge and the exchange test endpoint, not from a live fill; demo fill evidence depends on demo keys that are not present.
Authority: AK chat 2026-09-16; endpoint pr (commit, push, PR; no merge).
