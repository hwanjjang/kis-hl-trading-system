# Build — binance-usdm-ws (r1, 2026-09-16)

| Field | Recorded value |
| --- | --- |
| Task / stage / owner | binance-usdm-ws / build / main agent (Claude Fable 5.1) |
| Source / authority | AK request 2026-09-16; endpoint local |
| Consumed inputs | intent r1, spec r1, plan r1, test-plan, design (binance-user-stream-sequence) |
| Candidate | worktree sulky-dragonfly base 9360b0c + uncommitted files listed in logs/git-status.txt; diff in logs/change-record.diff |
| Status / decision | PROCEED to self-verification |

Plan mapping (plan.md → files):
- config: `kis_hl/config.py` `BinanceConfig`, `load_binance_config` (profile default/production, `BINANCE_TESTNET`, URL overrides, `recv_window_ms`).
- client: `kis_hl/binance/client.py` `BinanceFuturesClient` (public GET, HMAC signed GET, listenKey POST/PUT/DELETE, `normalize_symbol_filters`, `normalize_kline`, `sign_query`, `KLINE_INTERVALS`).
- ws: `kis_hl/binance/ws.py` stream builders, `market_stream_url`, `user_stream_url`, `BinanceMarketStreamClient`, `BinanceUserStreamClient` (fresh listenKey per connect via transport factory, keepalive on idle every 30 min, `listenKeyExpired` → raise → reconnect), `parse_market_ticks`, `OrderEvent`/`parse_order_event`/`order_event_to_row`.
- storage: `kis_hl/storage.py` `order_events` table + index, `store_order_event`, `list_order_events`.
- cli: `kis_hl/cli.py` `binance-info`, `binance-mark`, `binance-candles`, `binance-orders`, `binance-stream`, `binance-user-stream`, `binance-order-events`.
- docs/skill: `.env.example`, `README.md`, `docs/architecture.md`, `AGENTS.md`, `CLAUDE.md`, `.agents/skills/binance-api/` (+ symlink), `docs/architecture/binance-user-stream-sequence.{json,html}`.

Red → Green evidence: tests were written first and failed on import (`tests.test_binance_client`/`test_config`: 6 errors; `test_binance_ws`/`test_storage_order_events`: 2 errors), then passed after implementation (25, then 41, then 57 tests in scope). Two defects found and fixed during build: storage DDL split (index and table must be separate `execute` calls); `load_binance_config({})` fell back to `os.environ` because of `env or os.environ` (fixed to `None` check; test hardened to never print credential values).

Deviations from plan: none in scope. Smoke found that the system `python3` lacks `websocket-client`; a `.venv` (uv) was created for the websocket smoke only. Refactor step: none needed beyond the two fixes above.

## Iteration 2 (2026-09-16) — correction after independent verification

Findings consumed: `independent-verification.md` F1 (Must Fix), F2, F4, F5, F6. Main agent re-probed the routes: `/market` delivered aggTrade/kline/markPrice and zero bookTicker; `/public` delivered only bookTicker; the legacy unprefixed `/stream` root delivered only bookTicker.

Changes:
- `kis_hl/config.py`: new `BinanceConfig.ws_public_url` (`BINANCE_WS_PUBLIC_URL`, default `<ws>/public`).
- `kis_hl/binance/ws.py`: `PUBLIC_TIER_SUFFIXES`, `stream_route()`, and `market_stream_url()` now pick `/public` for bookTicker/depth and `/market` otherwise, and reject a mixed request with an actionable error; `time` imported at module top (F6).
- `kis_hl/cli.py`: `binance-stream` default `--streams mark`; help explains the route split; `binance-info` strips the symbol (F5).
- `kis_hl/storage.py`: DDL indentation aligned (F4).
- Tests: config/ws/cli updated and extended (`stream_route`, mixed-route rejection at ws and CLI level); 222 tests.
- Docs: README (separate `book` run), `.env.example`, `docs/architecture.md` (route partition; legacy root wording corrected per F2), skill SKILL.md and `references/websocket.md`.
- F3 (untracked generated artifacts under `docs/architecture/*.visual-check.*`, `.planning/`, `reports/`) is left for AK to decide at commit time; endpoint is local and nothing is committed.

## Iteration 3 (2026-09-16) — whitespace-only

QA iteration 2 residual nit: `protective_orders` DDL line indentation in `kis_hl/storage.py`. Re-indented one line inside a SQL string literal; no behavior change. Full suite re-run green (222).
