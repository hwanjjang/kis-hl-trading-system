# Spec — binance-order-execution (r1)

Intent r1. AC mapping: AC1 place_order; AC2 place_stop_market; AC3 place_trailing_stop; AC4 cancel_order; AC5 test_order/`--exchange-test`; AC6 guards; AC7 CLI + storage; AC8 config/docs/diagram/tests.

## Module: `kis_hl/binance/trading.py`
- `round_to_step(value: Decimal, step: Decimal, *, rounding=ROUND_DOWN) -> Decimal` (step > 0; result quantized to the step's exponent).
- `@dataclass(frozen=True, slots=True) BinanceOrderSubmission(status, dry_run, symbol, request, response)`; `status ∈ {dry_run, exchange_test, submitted, rejected}`.
- `submission_to_dict(submission) -> dict` adds `submitted_at_ms`; `extract_binance_order_id(response) -> str | None` (`orderId`).
- `class BinanceTradingClient(BinanceFuturesClient)`:
  - `__init__(config, *, timeout_seconds=10, now_ms=None)`; `live_symbols` from `config.live_symbols`.
  - `place_order(*, symbol, side, order_type, quantity, price=None, tif="GTC", reduce_only=False, client_order_id=None, dry_run=True, exchange_test=False, filters=None, mark_price=None)`.
  - `place_stop_market(*, symbol, side, stop_price, quantity=None, close_position=True, working_type="MARK_PRICE", client_order_id=None, dry_run=True, exchange_test=False, filters=None, mark_price=None)`.
  - `place_trailing_stop(*, symbol, side, quantity, callback_rate, activation_price=None, working_type="MARK_PRICE", client_order_id=None, dry_run=True, exchange_test=False, filters=None, mark_price=None)`.
  - `cancel_order(*, symbol, order_id=None, client_order_id=None, dry_run=True)`.
  - `position_mode_is_hedge() -> bool` (signed GET `/fapi/v1/positionSide/dual`).
  - Internal: `_prepare(...)` builds validated params; `_submit(path, params, *, dry_run, exchange_test)` implements the guard chain.

## Guard chain (every order method, in this order)
1. Pure validation (enums, positive Decimals, LIMIT needs price, client id pattern `^[A-Za-z0-9._:/-]{1,36}$`, else `kh` + uuid4 hex[:30]).
2. Filters: `filters` argument or `self.symbol_filters(symbol)` (public); `mark_price` argument or `self.premium_index(symbol)["markPrice"]` when needed (MARKET notional, stop direction).
3. Rounding: quantity ROUND_DOWN to `step_size`; BUY prices ROUND_DOWN, SELL prices ROUND_UP to `tick_size` (never more aggressive than requested). Checks: `min_qty ≤ qty ≤ max_qty` (`market_max_qty` for MARKET/STOP_MARKET/TRAILING), notional `qty × (price or mark) ≥ min_notional` (skipped for `closePosition`), stop direction (SELL stop < mark, BUY stop > mark), callback rate in [0.1, 10] with at most one decimal.
4. Build `request = {"path", "params", "client_request_id", "base_url", "key_profile"}`; **dry-run returns here** with `response={"skipped": "dry_run"}`.
5. `exchange_test`: `_require_credentials`, signed POST `/fapi/v1/order/test`, status `exchange_test` (no lock, no allowlist; it cannot place).
6. Live: allowlist (`symbol in config.live_symbols`) → credentials → one-way mode (`position_mode_is_hedge()` must be False) → `account_lock(config.base_url, config.api_key)` → signed POST/DELETE. A `RuntimeError` from the exchange becomes `status="rejected"`, `response={"error": msg}`; success is `status="submitted"` with the raw acknowledgement.

## Config (`kis_hl/config.py`)
- `BinanceConfig.live_symbols: tuple[str, ...] = ("BTCUSDT",)` from `BINANCE_LIVE_SYMBOLS` (comma list, upper-cased).
- `BINANCE_KEY_PROFILE=demo` selects `DEMO_BINANCE_APIKEY/SECRET` and the demo URLs unless `BINANCE_TESTNET=false` or explicit URL overrides are set.

## CLI (`kis_hl/cli.py`)
- `binance-trade --symbol --side buy|sell --order-type market|limit --quantity --price --tif --reduce-only --client-order-id --live --exchange-test --no-store` → `order_submissions` (venue `binance`, resolved_symbol = symbol, size = rounded qty, price = rounded price or None).
- `binance-stop --symbol --side --kind stop-market|trailing --stop-price --quantity --callback-rate --activation-price --reduce-only-quantity (disables closePosition) --working-type --source-submission-id --live --exchange-test --no-store` → `order_submissions` row plus `protective_orders` row (`order_type` STOP_MARKET|TRAILING_STOP_MARKET, `trigger_price` = stop or activation price or the mark price used, `covered_size` = quantity or `position`, `active = not dry_run and status == submitted`).
- `binance-cancel --symbol --order-id|--client-order-id --live --no-store` → `order_submissions` row (`order_type` cancel, `side` n/a).
- All handlers return `submission_to_dict` plus stored ids; no credential fields.

## Failure behavior
ValueError for argument/filter violations (before any signed call); RuntimeError for allowlist, credentials, hedge mode, lock contention; exchange HTTP errors surface as `rejected` submissions (not exceptions) so the CLI records them.

## Observability
`logger.info("binance_order_dry_run" | "binance_order_submitted" | "binance_order_rejected" | "binance_order_exchange_test")` with symbol, type, client id; never params containing secrets (there are none) and never the signature.

## Verification strategy
Unit tests with `RecordingClient` responses (exchangeInfo, premiumIndex, positionSide, order ack/error); guard-order tests with empty credentials; CLI tests with temp SQLite; smoke: dry-run CLI on mainnet public data, and `--exchange-test` with real keys (validates on the exchange without placing). No `--live` execution by the agent.

## Alternatives
Reusing `serialized_action` (rejected: needs `account_address`); putting trading into `client.py` (rejected: keep read/trade split like Hyperliquid).
