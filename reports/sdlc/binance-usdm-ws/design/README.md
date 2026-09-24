# Design — binance-usdm-ws (2026-09-16)

Diagram: `sequence` — "Binance User Data Stream Lifecycle". Decision it supports: the listenKey lifecycle is owned by the transport factory (fresh key per connection) plus an idle-tick keepalive, instead of adding key state to `MaintainedWebSocketClient`.

- Source JSON: `docs/architecture/binance-user-stream-sequence.json`
- Delivered HTML: `docs/architecture/binance-user-stream-sequence.html`
- Archify: installed skill at `/root/.claude/skills/archify` (`bin/archify.mjs`; update checker reported `current`).
- Commands: `validate sequence ... --quality showcase --json` (ok, 9 artifact checks, composition 0 errors / 0 warnings); `deliver sequence ... --json` (ok; spec sha256 df045da0…17bf 5416 bytes; artifact sha256 d9952af6…3cd7d 810044 bytes); `visual-check ... --json` with `ARCHIFY_CHROME=/root/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome` (ok, status pass; containment ok at 1440x900, 1600x1000, 1920x1080, 2048x1320 light and dark; receipt `docs/architecture/binance-user-stream-sequence.visual-check.json`, screenshots alongside).
- Element → spec/code mapping: `create_listen_key()` / `keepalive_listen_key()` → `BinanceFuturesClient` (`kis_hl/binance/client.py`); `connect /private/ws/<listenKey>` → `user_stream_url` + `_connect_with_fresh_listen_key` (`kis_hl/binance/ws.py`); `ORDER_TRADE_UPDATE` → `parse_order_event`; `store_order_event` → `kis_hl/storage.py`; `listenKeyExpired` → `_handle_raw_message` raising to force reconnect.
- Iterations: participant labels shortened (label width), timeline compacted twice (readable-timeline bound, then desktop containment at 1440x900/1600x1000). Final geometry: viewBox 1080x560, 11 messages at 28px spacing, 2 cards.
- Perceptual review: main agent viewed the 1440x900 light screenshot (see completion notes).
