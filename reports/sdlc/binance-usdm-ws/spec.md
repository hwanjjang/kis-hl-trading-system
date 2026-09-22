# Spec — binance-usdm-ws (r1)

Intent: reports/sdlc/binance-usdm-ws/intent.md r1. AC mapping: AC1 config; AC2 client; AC3 market ws + storage; AC4 user ws + order_events; AC5 CLI; AC6 docs; AC7 tests/smoke.

## Interfaces
- `kis_hl.config.BinanceConfig(base_url, ws_market_url, ws_user_url, api_key, api_secret, key_profile, recv_window_ms)`; `load_binance_config(env=None)`.
- `kis_hl.binance.client.BinanceFuturesClient(config, *, timeout_seconds=10, now_ms=None)`:
  - `get_public(path, params=None)`, `signed_get(path, params=None)`, `_request(method, path, params, *, signed, api_key_header)` (single transport seam `send(method, url, headers, body) -> (status, headers, text)` overridable in tests).
  - `exchange_info(symbol=None)`, `symbol_filters(symbol) -> dict(tick_size, step_size, min_qty, max_qty, min_notional, price_precision, quantity_precision, order_types, time_in_force)`, `premium_index(symbol)`, `book_ticker(symbol)`, `klines(symbol, interval, *, limit=500, start_time_ms=None, end_time_ms=None) -> list[dict(t,T,o,h,l,c,v,closed)]`, `server_time()`.
  - `account()`, `position_risk(symbol=None)`, `open_orders(symbol=None)`, `order_status(symbol, *, order_id=None, client_order_id=None)`.
  - `create_listen_key() -> str`, `keepalive_listen_key()`, `close_listen_key()`.
  - `sign_query(secret, query) -> hex` module function. Errors: `RuntimeError("Binance request failed: HTTP <code> <code>/<msg>")`; `ValueError` for bad args; `RuntimeError("Binance credentials are missing ...")` when key/secret empty.
- `kis_hl.binance.ws`: `mark_price_stream(symbol, *, fast=False)`, `book_ticker_stream`, `kline_stream(symbol, interval)`, `agg_trade_stream`, `market_stream_url(config, streams)`, `user_stream_url(config, listen_key)`; `BinanceMarketStreamClient(config, *, streams, on_message, transport_factory=None, stale_after_ms=15_000).run(max_messages, max_reconnects)`; `BinanceUserStreamClient(config, client, *, on_message, transport_factory=None, keepalive_interval_ms=1_800_000, now_ms=None, stale_after_ms=600_000).run(...)`; `parse_market_ticks(payload, *, received_at_ms) -> list[PriceTick]`; `OrderEvent` dataclass + `parse_order_event(payload, *, received_at_ms) -> OrderEvent | None`; `order_event_to_row(event)`.
- Storage: table `order_events(id, venue, symbol, order_id, client_order_id, side, order_type, execution_type, status, price, avg_price, orig_qty, last_filled_qty, cum_filled_qty, stop_price, reduce_only, event_time_ms, received_at_ms, payload_json)`; `store_order_event(db_path, *, ...)`, `list_order_events(db_path, *, venue=None, symbol=None, limit=50)`.
- CLI: `binance-info --symbol`, `binance-mark --symbol`, `binance-candles --symbol --interval --limit`, `binance-orders [--symbol]`, `binance-stream --symbol [--streams mark,book,kline:1h,trade] [--max-messages] [--max-reconnects] [--no-store]`, `binance-user-stream [--max-messages] [--max-reconnects] [--no-store]`, `binance-order-events [--symbol] [--limit]`.

## Behavior
- Normal: public calls need no credentials. Signed calls build `params + timestamp + recvWindow`, sign, append `signature`, send with `X-MBX-APIKEY`. listenKey calls send only the header.
- Failure: HTTP error -> RuntimeError including Binance `code`/`msg`; missing creds -> RuntimeError before any network call; bad interval -> ValueError listing valid intervals; unparsable tick values skipped silently (matches HL parser).
- Stale/reconnect: market client stale 15 s (markPrice@1s guarantees traffic); user client stale 10 min (quiet stream; server ping/pong keeps socket alive at transport level). Reconnect re-creates listenKey. `listenKeyExpired` raises inside the handler to trigger reconnect.
- Security: api_key/secret never logged or returned in CLI output; `binance-info` returns no credential fields.
- Observability: existing JSON logging (`logger.info("binance_...")`) for connect/keepalive/expired events.
- Migration: additive table via `init_db`; no changes to existing tables.

## Verification strategy
Unit tests with stubbed transport (request recording) and fake WebSocket transports; CLI tests via `main([...])` with patched client classes; smoke on public endpoints only.

## Alternatives
SUBSCRIBE-method subscriptions (rejected: needs state replay; URL form is replay-free). `binance-futures-connector` SDK (rejected: adds dependency; repo standard is urllib + stdlib hmac, and signing is simple).
