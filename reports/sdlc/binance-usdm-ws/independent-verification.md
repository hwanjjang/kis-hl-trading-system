# Independent verification — binance-usdm-ws

| Field | Value |
| --- | --- |
| Task | binance-usdm-ws |
| Stage / owner | independent-verification / QA subagent (separate context) |
| Date | 2026-09-16 |
| Consumed inputs | intent.md r1, spec.md r1, test-plan.md, `git status --short`, `git diff`, untracked `kis_hl/binance/`, `tests/test_binance_*.py`, `tests/test_storage_order_events.py`, `.agents/skills/binance-api/`, `.claude/skills/binance-api`, `docs/architecture/binance-user-stream-sequence.*` |
| ACs | AC1–AC7 |

No source, test, or doc file was modified. Only this report was written.

## Commands run and results

| Command | Result |
| --- | --- |
| `.venv/bin/python -m unittest discover -s tests -t . -q` | `Ran 220 tests in 11.079s — OK`, exit 0 (Python 3.11.15, websocket-client 1.9.2) |
| Fresh-DB script: `init_db` twice, `store_order_event`, `list_order_events` | 15 tables incl. `order_events` (19 columns), index `idx_order_events_venue_symbol_time`; roundtrip row id 1; `symbol="btcusdt"` filter matched uppercase row |
| `binance-info --symbol BTCUSDT` | exit 0; keys `filters, rate_limits, server_time, symbol`; tick 0.10, step 0.001, min notional 50; no credential fields |
| `binance-mark --symbol BTCUSDT` | exit 0; premium_index + book_ticker + `used_weight_1m: 2` |
| `binance-candles --interval 1h --limit 2` | exit 0; 2 normalized candles |
| `binance-candles --interval 3h` | exit 1, `Unsupported Binance kline interval '3h'; valid: 1m, ...` |
| `timeout 90 binance-stream --streams mark,book --max-messages 3 --no-store` | exit 0; connected to `.../market/stream?streams=btcusdt@markPrice@1s/btcusdt@bookTicker`; `ticks: {mark_price: 3}` — **zero bookTicker frames** |
| `binance-stream --streams book --max-messages 2 --max-reconnects 0` | no frames for 15 s → `websocket stream is stale`, disconnected |
| Raw websocket probes (4 s each, public) | `/market`: markPrice 4, aggTrade 45, kline_1m 10, **bookTicker 0, depth5 0**. Legacy `/stream` and `/ws`: bookTicker 300 (still served). Documented `/public/stream` and `/public/ws`: bookTicker 300 |
| Independent scripted checks (stubbed `send`, fake transports) | Signature == HMAC-SHA256(secret, exact query before `&signature=`); signed calls with empty key/secret raise `RuntimeError` before transport; listenKey POST/PUT/DELETE send only `Accept` + `X-MBX-APIKEY`, no body, no signature; `listenKeyExpired` → reconnect to URL built from a second fresh key, `status.url`/`last_error` contain no key; keepalive fires at 30:00 not 29:59, default 1,800,000 ms; 19 malformed `parse_market_ticks` inputs and 7 malformed `parse_order_event` inputs raised nothing |
| Network grep over tests | Only `*.example.test` hosts in transports; real hostnames appear only in `test_config.py` URL-string assertions; CLI tests patch `BinanceFuturesClient` / stream clients |
| Not run | `binance-orders`, `binance-user-stream` (operator credentials) |

## Findings

**F1 — Must Fix — default market websocket route drops `bookTicker` (and `depth`) silently.**
`kis_hl/config.py:20-23` and `load_binance_config` (`ws_default + "/market"`) route market data to `wss://fstream.binance.com/market`. Empirically that route delivers `markPrice`, `aggTrade`, `kline` but never `bookTicker`/`depth`, so the CLI default `--streams mark,book` (`kis_hl/cli.py:273`) and the README example stream only mark price, and `--streams book` reconnect-loops on staleness forever with no error. The official docs page now lists `wss://fstream.binance.com/public/ws/{stream}` and `/public/stream?streams=`; both served `bookTicker` at full rate in my probe. Fix: default `ws_market_url` to `<ws>/public` (`kis_hl/config.py`), update `.env.example` comment, `README.md` operational note, `docs/architecture.md:124`, `SKILL.md:36,40-41,119`, `references/websocket.md:5`. Unit tests cannot catch this; keep the `book` smoke in self-verification.

**F2 — Should Fix — factual claim "legacy `/ws` and `/stream` decommissioned on 2026-04-23" is wrong.** Both roots still serve full-rate `bookTicker` today (`docs/architecture.md:124`, `SKILL.md:40-41`, intent risk line, `investigation.md:9`). Replace with what was actually observed and cite the docs URL.

**F3 — Should Fix — generated visual-check artifacts staged for commit.** `docs/architecture/binance-user-stream-sequence.visual-check.{html,json,*.png}` (~700 KB of PNGs) plus `.planning/` and `reports/` are untracked. Decide explicitly which belong in the PR; the four PNGs and visual-check html/json look like build byproducts.

**F4 — Nit — DDL indentation.** `kis_hl/storage.py:115-140`: the new `order_events` block and the re-indented `protective_orders` line do not match surrounding statements (functionally valid).

**F5 — Nit — `cmd_binance_info` normalizes `symbol` with `.upper()` only** (`kis_hl/cli.py`, `cmd_binance_info`) while the client strips; `--symbol " btcusdt"` yields "not found" instead of a match.

**F6 — Nit — `_time_ms` in `kis_hl/binance/ws.py:409` imports `time` inside the function**; `kis_hl.streaming` already has the same helper.

Safety review: no order/cancel/modify/leverage path exists (`grep` finds only `GET /fapi/v1/order`); signed and listenKey paths fail closed; no `api_key`, `api_secret`, or `listenKey` appears in CLI output, `WebSocketStatus`, or log records (`logger.*` calls carry only event names / path / status); `POST`/`PUT` with `data=None` gets `Content-Length: 0` from `http.client`.

## AC verdicts

| AC | Verdict | Evidence |
| --- | --- | --- |
| AC1 | PASS | `BinanceConfigTests` (5) + scripted fail-closed checks for 3 credential combinations |
| AC2 | PASS | 16 client tests; signature/header/body verified independently; public smoke |
| AC3 | PARTIAL | Builders/parsers/storage pass; live `bookTicker` never arrives on the default route (F1) |
| AC4 | PASS (unit) | Fresh key per connect, 30-min keepalive, expiry reconnect, `order_events` roundtrip all verified; live stream not exercised |
| AC5 | PASS | Info/mark/candles smoke; `binance-orders` via patched-client test only |
| AC6 | PASS with F2 | Symlink resolves; AGENTS/CLAUDE/README/architecture/.env.example updated; SKILL method table matches client; decommission claim false |
| AC7 | PASS | 220/220, exit 0; public smoke OK |

## Limitations

- User-data stream (`/private/ws/<listenKey>`), `POST /fapi/v1/listenKey`, and signed reads were not exercised against a live/demo account; `ORDER_TRADE_UPDATE` shape is verified from fixtures only.
- The `/private` user route was not probed; given F1, confirm it against the current docs before relying on it.
- Testnet URLs were verified only as config values.

Iteration 1 verdict: FAIL (F1). Superseded by Iteration 2 below.

## Iteration 2 — re-verification after corrections (2026-09-16)

Inputs: updated working tree (`kis_hl/config.py` `ws_public_url`, `kis_hl/binance/ws.py` `PUBLIC_TIER_SUFFIXES`/`stream_route()`/`market_stream_url()`, `kis_hl/cli.py`, `kis_hl/storage.py`, tests, README, `.env.example`, `docs/architecture.md`, `SKILL.md`, `references/websocket.md`).

| Command | Result |
| --- | --- |
| `.venv/bin/python -m unittest discover -s tests -t . -q` | `Ran 222 tests in 8.621s — OK`, exit 0 |
| `binance-stream --streams mark,trade --max-messages 5 --no-store` | exit 0; url `.../market/stream?streams=btcusdt@markPrice@1s/btcusdt@aggTrade`; `ticks: {agg_trade: 4, mark_price: 1}` in 621 ms |
| `binance-stream --streams book --max-messages 5 --no-store` | exit 0; url `.../public/stream?streams=btcusdt@bookTicker`; `ticks: {book_ticker: 5}` in 95 ms |
| `binance-stream --streams mark,book --max-messages 1` | exit 1; error `Binance serves bookTicker/depth from the /public route and other market streams from /market; one connection cannot mix them. Run separate streams, e.g. --streams book and --streams mark,trade` |
| Raw route probes (5 s each) | `/public`: markPrice 0, aggTrade 0, depth5 10; `/market`: bookTicker 0; legacy `/stream`: markPrice 0, aggTrade 0 (bookTicker 300 in iteration 1) |

Finding status:
- **F1 — resolved.** Route partition is enforced in `market_stream_url()` with `test_market_stream_url_uses_combined_stream_form_per_route`, `test_market_stream_url_rejects_mixed_routes`, and CLI `test_binance_stream_rejects_mixed_route_streams`; default `--streams mark` streams live; `book` streams live on `/public`.
- **F2 — resolved, with a correction to my own iteration-1 claim.** The probes above show `/public` (and the legacy root) deliver only the bookTicker/depth tier, while `/market` delivers only markPrice/aggTrade/kline. My iteration-1 statement that `/public` "served bookTicker at full rate" was true but my implied conclusion that it could replace `/market` for all streams was wrong. The reworded text in `SKILL.md:41-44`, `docs/architecture.md:124`, `references/websocket.md:7-12`, and README:171-172 matches what I observed.
- **F3 — open by decision.** Generated artifacts, `.planning/`, and `reports/` are left for AK at commit time; not a code defect.
- **F4 — mostly resolved.** `order_events` DDL aligned; residual: `kis_hl/storage.py:140` `CREATE TABLE IF NOT EXISTS protective_orders (` now sits at 8 spaces versus 12 at HEAD:115 (cosmetic, DDL valid, tests pass). Nit.
- **F5, F6 — resolved** (`cli.py:628` strips before upper; `ws.py:5` imports `time` at module top).

Safety re-check: no new network path in tests (no `binance.com` host in transports); no credential or listenKey in CLI output or logs; still no order-placement path.

AC3 is now PASS (all four stream kinds parse from live frames; bookTicker and aggTrade verified live in this iteration, markPrice and kline in iteration 1). All other AC verdicts unchanged; AC4 remains PASS at unit level only.

VERDICT: PASS
