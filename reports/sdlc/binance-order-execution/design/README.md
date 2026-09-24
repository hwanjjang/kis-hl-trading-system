# Design — binance-order-execution (2026-09-16)

Diagram: `sequence` — "Binance Order Round Trip", refreshed from the planned version to the implemented guard chain. Decision it supports: validation/rounding before any signed call, dry-run return, then allowlist → credentials → one-way mode → account lock → signed POST; fills confirmed over the user stream.

- Source: `docs/architecture/binance-order-roundtrip-sequence.json`; delivered HTML alongside.
- Archify: validate ok (9 checks, 0 errors/warnings); deliver ok (artifact sha256 469c1c9f…0e5c, 813015 bytes); visual-check pass on 1440x900, 1600x1000, 1920x1080, 2048x1320 light and dark; main agent viewed the 1440x900 screenshot.
- Element → code: `place_order/place_stop_market/place_trailing_stop` → `kis_hl/binance/trading.py`; `symbol_filters() + premium_index()` → `kis_hl/binance/client.py`; guard labels → `BinanceTradingClient._submit`; `order_submissions/protective_orders` → `kis_hl/storage.py`; `store_order_event` → `kis_hl/binance/ws.py` + storage.
- Iterations: participant sublabel shortened twice for desktop readability.
- Evidence: browser receipt kept at reports/sdlc/binance-order-execution/design/visual-check.json (docs/ keeps only json + html per .gitignore policy).
- Iteration 3 (2026-09-19): labels updated for the Algo Order path and outcome classes (validate 9/9, deliver ok, visual-check pass; receipt refreshed under reports/design/).
