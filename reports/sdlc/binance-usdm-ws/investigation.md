# Investigation — binance-usdm-ws (2026-09-16)

Question: what does the repo already provide, and what do Binance USDⓈ-M REST/WS contracts look like, so the integration mirrors existing patterns?

Verified facts (code): see .planning/2026-09-16-binance-usdm-ws-data-plane/findings.md "Repo facts". Key: `MaintainedWebSocketClient` accepts `transport_factory(url, timeout)` and `on_idle`; ticks are `PriceTick`; storage is vendor-neutral with `source`; config loaders take an env mapping; CLI handlers return dicts.

Verified facts (vendor, live public probes on 2026-09-16): BTCUSDT filters (tick 0.10, step 0.001, min notional 50), order types incl. TRAILING_STOP_MARKET, rate limits 2400 weight/min, klines 3h invalid, demo-fapi testnet reachable, `x-mbx-used-weight-1m` header present.

Verified facts (docs): signature = HMAC-SHA256 over query string incl. timestamp/recvWindow; `X-MBX-APIKEY` header; listenKey valid 60 min, PUT extends; user stream URL `wss://fstream.binance.com/private/ws/<listenKey>`; market URL `wss://fstream.binance.com/market` with `/ws/<stream>` or `/stream?streams=`; legacy URLs decommissioned 2026-04-23; server ping every 3 min; ORDER_TRADE_UPDATE execution types NEW/CANCELED/CALCULATED/EXPIRED/TRADE/AMENDMENT; statuses NEW/PARTIALLY_FILLED/FILLED/CANCELED/EXPIRED/EXPIRED_IN_MATCH.

Hypotheses (not verified live): exact single-letter keys of ORDER_TRADE_UPDATE `o` object (s, c, S, o, x, X, i, p, ap, q, l, z, L, sp, R, T, t, rp) follow the long-standing schema; parser is written defensively and tolerates missing keys.

Implication: implement as planned; mark user-stream shape as an open risk in docs until a testnet session confirms it.
