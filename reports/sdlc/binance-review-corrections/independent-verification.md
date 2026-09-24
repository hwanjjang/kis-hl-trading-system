# Independent verification — PR18 correction candidate

Baseline HEAD `7efe632`; inspected working changes plus integrated PR17 fixes.
Read-only source audit with mocked/unit tests only. No vendor calls, signed requests, live orders, source edits, commits or publication. This report is not live exchange verification.

## Initial verdict: CHANGES REQUIRED (two small corrections)

1. **Explicit dry-run can send a signed request when combined with exchange-test.** In `kis_hl/cli.py`, `--exchange-test` is outside the mode mutually-exclusive group; `--dry-run --exchange-test` is accepted. `_submit` processes exchange_test before dry_run and sends signed `POST /fapi/v1/order/test`. This does not place an order, but breaks the newly advertised explicit preview/no-signed-call contract. Put `--exchange-test` in the CLI mode group and add a parser/dispatch rejection test. Python API exchange_test semantics can remain as documented.
2. **F44 remains partially unfixed.** `docs/architecture/binance-trading-data-flow.json:49` says "... and be audited; not implemented yet" and its card at line 331 says "No Binance order placement yet; dashed elements are the next iteration". Both appear in generated HTML. Correct these implemented-order statements and regenerate. Also scope README line 410's "Live trading is opt-in with --live" to the venues for which that is still true; Binance's new default contradicts the unqualified statement.

Additional small documentation correction: `references/websocket.md` still omits CANCELED from ALGO_UPDATE states (F15). In `orders.md`, the regular RESULT status list still omits REJECTED/EXPIRED_IN_MATCH and the test-endpoint `{}` response claim remains absolute although no successful response was observed (recommended F58). The outcome table says -1007 "with unknown-execution wording", whereas code treats that code as unknown regardless of message; qualify only -1000/-1006 wording or reflect the actual regex.

## Passing checks

- `.venv/bin/python -m unittest tests.test_binance_order_review tests.test_binance_trading tests.test_binance_review_regressions tests.test_cli -q`: **106 passed**.
- Extra mocked CLI dispatch probe, with environment cleared: both `binance-stop` and `binance-cancel` pass `dry_run=False` by default and `True` with `--dry-run`. New committed-candidate test verifies `binance-trade` similarly. No network involved.
- **F02:** supported live set is code-pinned to BTCUSDT; environment can only narrow. Fresh metadata before POST must match symbol, TRADING, PERPETUAL and COIN; negative tests prevent mutation for contrary metadata. Missing fields fail closed. Cancellation retains recovery behavior without current trading-status metadata.
- **Protection direction/coverage (C01):** conditional live requests read position inside the account lock, require exactly one BOTH-mode position with finite nonzero amount, correct closing side, and explicit quantity equal to full current position. Tests reject flat/opposite/undercovered positions. Snapshot limitations and independent account writers are documented.
- **F07:** immediate terminal/no-fill POST responses become rejected, partial fills remain submitted, consistent with existing one-shot reconciliation. Unknown/rejected protection rows stay inactive and return exit codes 3/2 in new CLI tests.
- **F52:** signed POST test uses a recording lock context and asserts execution occurs inside it; removal of lock invocation is observable. Cancel-algo allowlist test asserts zero network calls before rejection.
- **F15 core:** obsolete conditional POST /order paragraph replaced by correct regular/algo family index; missing wrapped reads documented; error-code mapping and conservative retry documentation updated.
- **F16:** architecture now says unit/dry-run evidence only and prior signed test returned -2015. No successful exchange validation or demo/live fill is claimed.
- **F29:** skill no longer grants agent execution authority; links applicable rules.
- **F43:** owner outcome reference now covers terminal acknowledgements and unknown reconciliation; README links it, warns client ID reuse is not durable idempotency; no automatic unknown-protection recovery is claimed.
- **Credential isolation:** BinanceOrderCliTests blocks .env loading, replaces environment with sentinel keys and asserts sentinel values/signature absent from output. Config secret fields remain repr-hidden. No credential output observed in targeted tests.
- **Default behavior:** prior explicit user request justifies live-default CLI; direct Python methods retain dry defaults. Independent tests called mocks only.

## PR17 handshake correction recheck

Previously noted private-WebSocket permanent handshake issue is now corrected: transport exceptions with status_code 400/401/403/418/429 become sanitized PermanentWebSocketError. New handshake rejection test passed in the 106-test run, as did quiet renewal and auth-error secrecy tests. Ordinary transport failures remain retriable. Prior PR17 report's recommended edge case is resolved.

## Limits and residual scope

No successful live/demo auth, fills, algo response-shape verification, or trigger execution proven. Environment/account-scoped historical data, persistence throughput, pre-send durable intents and full recovery remain separately documented deferred work. Malformed exchange response/matching-client-ID reconciliation hardening is outside this bounded correction verification. Final receipt should bind results to the committed candidate, not just this changing working tree.

## Reverification after corrections — PASS

The initial two required corrections are resolved in the current working tree:

- `--exchange-test` now belongs to the same mutually-exclusive CLI mode group as `--dry-run` and `--live`. `OrderCliReviewTests.test_dry_run_and_exchange_test_cannot_be_combined` verifies parser rejection; no handler or transport executes for the conflicting flags.
- Dataflow JSON and delivered HTML no longer contain "not implemented yet" or "No Binance order placement yet". The trading view/card explicitly state that order placement is implemented while strategy automation remains planned.
- README's opt-in safety sentence is now venue-scoped and explicitly states Binance's send-by-default / `--dry-run` behavior.
- ALGO_UPDATE lifecycle reference now includes CANCELED.

Independent rerun: `.venv/bin/python -m unittest tests.test_binance_order_review tests.test_binance_review_regressions -q` — **21 tests passed**. The prior 106-test run remains the broader evidence for unchanged checks; this rerun targets the new correction and integrated PR17 regressions.

**Final independent verdict: PASS for the bounded PR17/PR18 review-correction scope; no remaining Must Fix identified.** Earlier small F58 documentation observations and explicitly deferred architecture/lifecycle work remain recommendations/limitations rather than blockers. No external provider launch was attempted; this is same-provider independent verification, not a cross-provider review. The automatic approval rejection of a separate cross-provider launch is outside this verifier's evidence and must not be described as a successful review.
