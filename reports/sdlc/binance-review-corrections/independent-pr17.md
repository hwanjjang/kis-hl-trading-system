# PR17 independent verification — working tree corrections

Baseline: `b149a52876a0c6568773dbf3e6fce118041c87fd`; branch `review-binance-mcp-issue`.
Inspected working diff including untracked `tests/test_binance_review_regressions.py`.
Independent verifier did not edit source, commit, publish, or execute vendor calls.

## Verdict

**PASS for original Must Fix correction scope (F01, F09, F45); one remaining recommended F10 edge case.** No new must-fix regression found in the bounded review. F18 was already resolved by the earlier merge.

## Evidence

- `.venv/bin/python -m unittest tests.test_binance_review_regressions tests.test_binance_ws tests.test_binance_client tests.test_config tests.test_cli -q`: **76 passed**.
- `.venv/bin/python -m unittest tests.test_websocket_streams tests.test_trailing_stream -q`: **7 passed**; shared runner change preserves tested KIS/Hyperliquid behavior.
- An initial test invocation included nonexistent `tests.test_streaming` and failed to import that module; rerun with the correct modules above passed. This was verifier command selection, not candidate failure.
- Read builder's `/tmp/binance-stream-smoke.py`: real loopback REST and WebSocket wiring plus SQLite event storage; no vendor endpoint. Its reported execution was not rerun independently, and the report does not claim otherwise.
- Additional stub-only probe: REST listenKey creation failures HTTP 401/-2015, 403 and 429 each raise `PermanentWebSocketError` after exactly one call, with zero socket attempts and zero reconnect sleeps.
- Additional stub-only probe: a message arriving when renewal gets HTTP 401/-2015 is delivered exactly once before the fatal error is propagated.
- New quiet-stream regression advances fake time to minute 31 and asserts one connection, one renewal, received event and no listenKey in status. Disabling message staleness specifically for Binance private stream permits renewal without suppressing transport-close detection.
- Transient renewal test verifies event-before-renewal and no immediate second renewal. Inspection confirms the next attempt is delayed 60 seconds and the 55-minute deadline forces reconnect.
- Binance config secrets use dataclass `repr=False`; CLI Binance tests both suppress `.env` loading and clear the inherited environment. The mixed-tier failure test stubs the actual socket factory and bounds reconnects, so removing route rejection cannot accidentally connect indefinitely.

## Recommended remaining edge case

`kis_hl/binance/ws.py`, `_connect_with_fresh_listen_key`, transport exception handler:

A permanent **WebSocket handshake** rejection (rather than a listenKey REST rejection) is caught by `except Exception` and replaced with generic `RuntimeError("Binance private websocket connection failed")`. The maintained runner retries it forever by default. A stub factory raising `RuntimeError("Handshake status 401 Unauthorized")` produced three new listenKey calls and two retries with `max_reconnects=2`.

The implemented F10 fix is therefore complete for missing credentials and REST create/renew auth/ban/rate-limit failures, but does not cover permanent private-socket handshake failures. Suggested surgical follow-up: inspect a real websocket exception's `status_code` attribute for 401/403/418/429, raise sanitized `PermanentWebSocketError`, and add a test asserting one key request and no sleep. Keep ordinary connection timeouts retriable; do not parse/emit the raw URL containing the key. Alternatively describe the fixed boundary precisely in the disposition report and defer this edge case explicitly.

## Scope limits

No claim of successful Binance user-stream authentication, field validation against a live account, exchange fills, or resolution of acknowledged schema/throughput/persistence follow-ups. The generic runner still treats storage callback failures as disconnects, which is the separately reviewed F25 behavior. This review is a snapshot of uncommitted corrections; final commit/receipt should bind the recorded test results to the eventual candidate revision.
