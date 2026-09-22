# Build — binance-order-execution (r1, 2026-09-16)

| Field | Recorded value |
| --- | --- |
| Task / stage / owner | binance-order-execution / build / main agent (Claude Fable 5.1) |
| Source / authority | AK chat 2026-09-16; endpoint pr |
| Consumed inputs | intent r1, spec r1 (amended: trailing trigger_price text, exchange-test rejection), plan r1, test-plan, design |
| Candidate | branch binance-order-execution base 1b2a337 + uncommitted files (logs/git-status.txt, logs/change-record.diff) |
| Status / decision | PROCEED to self-verification |

Plan mapping:
- `kis_hl/binance/trading.py` (new): `round_to_step`, `BinanceOrderSubmission`, `submission_to_dict`, `extract_binance_order_id`, `BinanceTradingClient` with `place_order`, `place_stop_market`, `place_trailing_stop`, `cancel_order`, `position_mode_is_hedge`, `_submit` guard chain, validation helpers.
- `kis_hl/config.py`: `live_symbols` (`BINANCE_LIVE_SYMBOLS`), `demo` key profile with demo URL default.
- `kis_hl/cli.py`: `binance-trade`, `binance-stop`, `binance-cancel`, `_store_binance_submission`.
- Tests: `tests/test_binance_trading.py` (new, 25 tests), `tests/test_config.py` (+2), `tests/test_cli.py` (+4).
- Docs: README (commands, safety notes), `docs/architecture.md`, `.env.example`, skill SKILL.md + `references/orders.md`, diagram `binance-order-roundtrip-sequence` refreshed.

Red → Green: tests written first failed on import/attribute (3 errors config+trading, 4 errors CLI); Red re-executed against base 1b2a337 with the new test files (7 errors, exit 1, `logs/unittest-red-base.log`). Green after implementation; adjustments during build: rounding expectations aligned to quantize-to-step output ("75000.00"), cancel skips the position-mode read, exchange-test errors are recorded as `rejected` submissions (found by smoke: the operator key is IP/permission-restricted from this host, HTTP 401 -2015).

Deviations: none in scope. Not done: demo fill (no demo keys), live order (agent never runs `--live`).

Spec deviations (spec r1 kept as the consumed revision): (1) trailing stops without an activation price store `trigger_price` as `callback:<rate>%` rather than the mark price, which would have misrepresented a trigger level; (2) an exchange error during `exchange_test` is returned as a `rejected` submission with `dry_run=true`, matching the live path, so the CLI records it instead of exiting with an exception.

## Iteration 3 (2026-09-16) — QA Should Fix items

- `position_mode_is_hedge()` now raises unless the response carries an explicit boolean `dualSidePosition` (fail closed on `{}`, `[]`, `null`, empty body).
- `BINANCE_LIVE_SYMBOLS=""` yields an empty allowlist, which disables live Binance orders; the default applies only when the variable is unset. README and `.env.example` say so.
- Non-finite Decimals (NaN, Infinity) raise `ValueError`; client order ids use `fullmatch` (no trailing newline); `close_position=True` with a quantity is rejected explicitly.
- Tests added for each; suite 249 tests. Remaining QA nits (MARKET_LOT_SIZE step, trailing activation direction, `--exchange-test` exit code, spec wording) are deferred as follow-ups and listed in completion.md.

## Iteration 4 (2026-09-19 → 2026-09-20) — corrections from the Codex PR review (rounds 1–9)

Commits 3bd980d, 8b95376, ae22acd, 097f353, 683c35b, a4510f7, ca59dae, 1d7d3a4, bc454f4 (see pr-review.md table). Each change: red test against the previous head (`logs/unittest-red-correction*.log`), then implementation, then the full suite. Final suite: 280 tests. Deferred with reason: ALGO_UPDATE user-stream parsing (schema not verifiable offline; documented open risk).
