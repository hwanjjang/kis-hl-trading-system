# Intent — binance-usdm-ws (r1, 2026-09-16)

Problem: the system executes only on Hyperliquid. AK wants to trade BTC on Binance USDⓈ-M futures. Before any order placement, the runtime needs a Binance data plane: public market data, signed read-only account/order reads, and WebSocket delivery of both prices and order-status events into SQLite.

Outcome: `python -m kis_hl.cli binance-*` commands work against mainnet/testnet using existing `.env` credentials, with no order placement, no secrets printed, and unit tests that never touch the network.

Acceptance criteria:
- AC1 `load_binance_config` selects `BINANCE_APIKEY/SECRET` (default) or `PRO_BINANCE_*` (`BINANCE_KEY_PROFILE=production`), rejects other profiles, picks demo URLs when `BINANCE_TESTNET=true`, honors URL overrides; signed calls fail closed with a clear error when credentials are empty.
- AC2 `BinanceFuturesClient` provides exchange_info/symbol_filters, premium_index, book_ticker, klines (interval validated; 3h rejected), server_time; signed read-only account, position_risk, open_orders, order_status with HMAC-SHA256 signature over the exact query string; listenKey create/keepalive/close with API-key header and no signature. All request construction is unit-tested with a stubbed transport.
- AC3 Market WebSocket: combined-stream URL builder for markPrice/bookTicker/kline/aggTrade; payloads parsed into `PriceTick(source="binance")`; CLI `binance-stream` stores ticks in `market_ticks` (source `binance`, market `usdm_futures`).
- AC4 User-data WebSocket: listenKey obtained per connection, keepalive every 30 min, `listenKeyExpired` forces reconnect with a fresh key; `ORDER_TRADE_UPDATE` parsed into a normalized order event and stored in a new `order_events` table; CLI `binance-user-stream` runs it and `binance-order-events` lists stored rows.
- AC5 CLI read-only commands `binance-info`, `binance-mark`, `binance-candles`, `binance-orders` return JSON via the existing handler contract.
- AC6 Docs/skill: `.agents/skills/binance-api/` with `.claude/skills/binance-api` symlink, AGENTS.md usage rule, CLAUDE.md ownership row and working rule, README env + commands, docs/architecture.md component lines, `.env.example` placeholders.
- AC7 `python3 -m unittest discover -s tests -t . -q` passes; public-endpoint smoke of `binance-info`/`binance-mark` succeeds.

In scope: the above. Out of scope: order placement/cancel/modify, leverage changes, spot, MCP configuration, Korea regulatory analysis, commits/PR.
Constraints: stdlib urllib + hmac, websocket-client transport, sync code, Decimal for prices, English artifacts, no secrets in output.
Assumptions: `.env` credential names as reported by AK; mainnet public endpoints reachable from this host (verified).
Risks: user-data-stream shape verified from docs, not a live session; Binance WS legacy URLs decommissioned 2026-04-23 so routed `/market` and `/private` URLs are used.
Authority: AK's chat request; endpoint local.
