# Self-verification — binance-usdm-ws (2026-09-16)

| Field | Recorded value |
| --- | --- |
| Task / stage / owner | binance-usdm-ws / self-verification / main agent (same context as builder) |
| Consumed inputs | build.md, test-plan.md, candidate files (logs/git-status.txt) |
| Environment | Linux, system python3 (3.11+), `.venv` via uv with websocket-client 1.9.2 for websocket smoke only |
| Status / decision | PROCEED to independent verification |

Commands and results (raw output in `logs/`):
- `python3 -m unittest discover -s tests -t . -q` → `Ran 220 tests`, OK, exit 0 (`logs/unittest-full.log`, `logs/unittest-exit.txt`).
- `python3 -m unittest tests.test_binance_client tests.test_binance_ws tests.test_storage_order_events tests.test_config tests.test_cli -q` → `Ran 68 tests`, OK (`logs/unittest-scope.log`).
- Public smoke (`logs/smoke-public.log`): `binance-info` returns tick 0.10 / step 0.001 / min notional 50 and the three rate limits; `binance-mark` returns mark, bid, ask and used weight; `binance-candles --interval 1h --limit 2` returns 2 rows; `--interval 3h` is rejected with the valid-interval list; `binance-stream --streams mark,book --max-messages 3 --no-store` connected once (no reconnects, no error) and parsed 3 mark-price ticks from the live public stream.
- Skill discovery: `.claude/skills/binance-api/SKILL.md` resolves through the symlink and the host listed `binance-api` as an available skill in-session.
- Design: `archify validate/deliver` receipts and `visual-check` receipt in `docs/architecture/binance-user-stream-sequence.visual-check.json` (see design/README.md for the final status).

AC coverage: AC1 config tests (5) + fail-closed client test; AC2 client tests (14) + public smoke; AC3 ws parser/client tests + CLI store test + live stream smoke; AC4 user-stream lifecycle tests (2), parser tests, storage roundtrip, CLI store/list tests; AC5 CLI tests (4); AC6 files present and cross-referenced; AC7 full suite green.

Not exercised: `binance-orders` and `binance-user-stream` against the real account (would use operator credentials); the user-data-stream schema is verified only against docs and fixtures.

## Iteration 2 (2026-09-16) — after route correction

- `python3 -m unittest discover -s tests -t . -q` → `Ran 222 tests`, OK, exit 0 (`logs/unittest-full.log`).
- Scope suites → OK (`logs/unittest-scope.log`).
- Public smoke (`logs/smoke-public.log`): `binance-stream --streams mark,book` now rejected with the route explanation; `--streams mark,trade` connected to `.../market/stream?...` and parsed 1 mark + 4 aggTrade ticks; `--streams book` connected to `.../public/stream?...` and parsed 5 bookTicker ticks; no reconnects, no errors.

## Iteration 3 (2026-09-16)

- `python3 -m unittest discover -s tests -t . -q` → `Ran 222 tests`, OK, exit 0 after the whitespace-only storage.py change (`logs/unittest-full.log` refreshed).
