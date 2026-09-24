# Self-verification — binance-order-execution (2026-09-16)

| Field | Recorded value |
| --- | --- |
| Task / stage / owner | binance-order-execution / self-verification / main agent (same context as builder) |
| Consumed inputs | build.md, test-plan.md, candidate files |
| Environment | Linux, system python3 3.12; mainnet public endpoints for dry-run smoke; operator key for the exchange-test call |
| Status / decision | PROCEED to independent verification |

- `python3 -m unittest discover -s tests -t . -q` → Ran 247 tests, OK, exit 0 (`logs/unittest-full.log`).
- Scope suites → Ran 63 tests, OK (`logs/unittest-scope.log`).
- Red against base: 7 errors, exit 1 (`logs/unittest-red-base.log`).
- Smoke (`logs/smoke-orders.log`): limit dry-run rounded 0.0019→0.001 and 60000.07→60000.00 and stored row 1; market 0.0005 rejected below minQty; stop-market closePosition dry-run stored protective row 1 (trigger 60000.00, covered `position`, linked to submission 1); trailing dry-run stored protective row 2 (callback:1.5%); wrong-direction stop rejected against live mark; cancel dry-run stored; `--exchange-test` reached Binance and was answered HTTP 401 -2015 (key IP/permission restriction on this host), recorded as a `rejected` submission with `dry_run=true`, no order placed.
- AC coverage: AC1–AC4 unit + dry-run smoke; AC5 unit + real signed call to `/order/test` (rejected by key policy, path verified); AC6 ordered guard tests; AC7 CLI tests + smoke rows; AC8 config tests, docs present, diagram refreshed, suite green.
- Not exercised: a successful exchange-test or fill (needs a key allowed from this IP with futures permission, or demo keys); `--live` by design.

## Iteration 2 (2026-09-16) — after QA fixes

- `python3 -m unittest discover -s tests -t . -q` → Ran 249 tests, OK (`logs/unittest-full.log`); scope suites 65 OK.
- Smoke evidence from iteration 1 remains valid: the changed code paths (position-mode parsing, empty allowlist, non-finite inputs) are unreachable from the dry-run smoke and are covered by the new unit tests.

## Iteration 3 (2026-09-20) — final candidate bc454f4 after review corrections

- `python3 -m unittest discover -s tests -t . -q` → Ran 280 tests, OK (`logs/unittest-full.log`); scope suites 112 OK (`logs/unittest-scope.log`).
- Red evidence per correction round retained in `logs/unittest-red-correction*.log` (each run against the previous head with the new tests, all exit 1).
- Final dry-run smoke (`logs/smoke-final.log`): entry LIMIT → `/fapi/v1/order`; stop-market and trailing → `/fapi/v1/algoOrder` with `algoType=CONDITIONAL`; cancel algo dry-run; rows in `order_submissions` (4) and `protective_orders` (2, inactive because dry-run); route probe `/fapi/v1/openAlgoOrders` and `/fapi/v1/algoOrder` answer 401 (routes exist).
- Earlier smoke (iteration 1, `logs/smoke-orders.log`, `logs/smoke-correction.log`) remains valid for the unchanged paths (rounding, rejections, exchange-test rejection by key policy).
- Final head 7ffb790 (QA it.2 doc/CLI fixes): full suite 282 OK, scope 114 OK; logs refreshed.
