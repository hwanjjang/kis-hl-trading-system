# Independent verification — binance-order-execution

| Field | Value |
| --- | --- |
| Task | binance-order-execution (branch `binance-order-execution`, base 1b2a337, uncommitted diff) |
| Stage / owner | independent-verification / QA subagent (separate context) |
| Date | 2026-09-16 |
| Inputs consumed | intent.md (AC1–AC8), spec.md (r1, incl. exchange_test-rejected update), test-plan.md, `git diff`, `kis_hl/binance/trading.py` (md5 7f3e0178), `tests/test_binance_trading.py` (md5 392a9000), `kis_hl/cli.py` (md5 da76e780), `kis_hl/config.py`, `kis_hl/execution_lock.py`, README, docs/architecture.md, skill SKILL.md + references/orders.md, `.env.example`, round-trip diagram JSON/HTML |
| ACs | AC1–AC8 |

## Commands and results

| Command | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -t . -q` (after coordinator's exchange_test change) | `Ran 247 tests … OK`, exit 0 (earlier run: 246 OK) |
| `/tmp/qa-bin/probe.py` (60 boundary / malformed-input cases against `RecordingTradingClient`, no network) | see findings; signature check `True` over exact key order `symbol…reduceOnly,recvWindow,timestamp`; lock contention -> `RuntimeError('Account has another execution owner')`, no POST; positionSide 503 -> RuntimeError before lock, no POST; `dry_run=False, exchange_test=True` -> only `POST /fapi/v1/order/test` |
| `binance-trade --symbol btcusdt --side buy --order-type limit --quantity 0.0021 --price 60000.07` (dry-run, temp DB, mainnet public data) | exit 0, `quantity 0.002`, `price 60000.00`, row `('binance','BTCUSDT','BUY','LIMIT','0.002','60000.00',1,'dry_run')` |
| `binance-stop --side sell --kind trailing --quantity 0.002 --callback-rate 1.5` (dry-run) | exit 0, `reduceOnly true`, protective row `('TRAILING_STOP_MARKET','callback:1.5%','0.002',1,0,'dry_run')` |
| `binance-stop --side sell --kind stop-market --stop-price 999999` (dry-run) | exit 1, `SELL stop 999999.00 must be below the mark price 76093.01…` (fails closed before any signed call) |
| `binance-trade --side buy --order-type market --quantity 0.002 --exchange-test --no-store` | exit 0, `status: rejected`, `dry_run: true`, response `HTTP 401 -2015/Invalid API-key, IP, or permissions` — key is IP-restricted/unpermitted from this host; no order possible |
| `grep` real hosts in tests | only URL-constant assertions in `test_config.py` and Hyperliquid config literals; Binance trading/CLI tests use `example.test`, CLI tests stub `send` to raise `AssertionError` |

## Findings

No Must Fix items.

### Should Fix

1. **Hedge-mode guard fails open on a missing field.** `kis_hl/binance/trading.py:231-232` `return bool(isinstance(payload, dict) and payload.get("dualSidePosition"))`. Probe: positionSide responses `""`, `{}`, `[]`, `null` all produced `status=submitted` with a `POST /fapi/v1/order`. AGENTS.md requires live paths to fail closed; an unverifiable position mode should raise. Real-money exposure is limited (a hedge account would get `-4061` -> `rejected`), but the guard contradicts its own contract. Suggest requiring the key to be present and boolean.
2. **Empty allowlist silently re-enables BTCUSDT.** `kis_hl/config.py:186-190` `… ) or ("BTCUSDT",)`. `BINANCE_LIVE_SYMBOLS=""` (or `" , "`) yields `("BTCUSDT",)`, so an operator cannot disable live trading through the allowlist; `.env.example` describes it as the allowed list. Suggest empty -> `()`; keep the default only when the variable is absent.
3. **Non-finite Decimals escape as `decimal.InvalidOperation`.** `trading.py:311-320` `_positive` only guards construction; `Decimal("NaN")`, `sNaN`, `Infinity` for quantity/price/callback_rate raise `InvalidOperation` from the `<= 0` comparison or `quantize`. CLI still exits 1 (generic catch, message `[<class 'decimal.InvalidOperation'>]`), so it is safe, but spec says argument violations are `ValueError`.

### Nit

- `trading.py:326` `CLIENT_ORDER_ID_RE.match` with `$` accepts `"abc\n"`; use `fullmatch`.
- `trading.py:145-166` `place_stop_market(close_position=True, quantity=…)` silently drops `quantity` (CLI ties `close_position=not args.quantity`, so only the library surface is affected).
- `place_trailing_stop` performs no MIN_NOTIONAL check and no activation-direction check; a SELL `activationPrice` rounds up (activates later), so the `_round_price` docstring's "triggers earlier" claim does not cover activation. Both surface as exchange `rejected` (`-4164`/`-2021`).
- `_round_quantity` uses `LOT_SIZE` step/min for MARKET-type orders; `MARKET_LOT_SIZE` step/min are ignored (identical on BTCUSDT today).
- `--exchange-test` returning `rejected` exits 0 (observed in smoke); scripts cannot distinguish by exit code. The `-2015` message also echoes the caller's public IP into stored/printed output.
- Spec drift only: spec.md still names an internal `_prepare(...)` and a `--reduce-only-quantity` flag; implementation validates per method and uses `--quantity` to disable `closePosition`. README/skill/orders.md match the code.

## Verified behaviours (no issues)

Dry-run is the default and makes no signed call (only public `exchangeInfo`/`premiumIndex`, no `X-MBX-APIKEY`). Guard order confirmed: validation -> dry-run return -> allowlist -> credentials -> one-way mode -> `account_lock` -> signed request (`trading.py:261-279`, tests `LiveGuardTests`). Exchange HTTP errors become `rejected` (live `dry_run=False`; exchange_test `dry_run=True`, coordinator's change covered by `test_exchange_test_error_becomes_rejected_submission`). `exchange_test` hits only `/fapi/v1/order/test` and wins over `dry_run=False`. `closePosition` orders carry neither `quantity` nor `reduceOnly`; TRAILING is `reduceOnly=true` with `callbackRate` 0.1–10, one decimal (`1.50` -> `1.5`, `10` -> `10.0`, `1E+3` rejected). Rounding: qty ROUND_DOWN to step (`1E-3`, `2E+1`, `0.0010000000` all normalise), BUY prices down / SELL prices up to tick; boundaries at exactly minQty, market_max_qty 120 and notional 50 accepted, `120.0004` rounds to `120.000`. Stop direction uses the rounded stop (`75999.95` SELL rounds to mark and is rejected). `newClientOrderId` always present (`kh`+30 hex = 32 chars). Signed query covers exactly the sent params; `cancel_order` uses `DELETE /fapi/v1/order` with `orderId` or `origClientOrderId`, honours allowlist and credentials, skips the position-mode call. CLI output contains `base_url`/`key_profile` only, no key/secret/signature. Config: demo profile selects `DEMO_BINANCE_*` and demo URLs, `BINANCE_TESTNET=false` overrides. Docs: README commands/safety notes, architecture.md, SKILL.md sections 0 and 3, `references/orders.md`, `.env.example`, and the diagram JSON/HTML (title no longer "planned", guard chain named) are consistent with the code.

## AC verdicts

| AC | Verdict | Note |
| --- | --- | --- |
| AC1 place_order | Pass | rounding, minQty/maxQty/MIN_NOTIONAL, client id, dry-run/live/rejected |
| AC2 place_stop_market | Pass | closePosition params, reduce-only variant, direction vs mark |
| AC3 place_trailing_stop | Pass | callbackRate bounds/decimals, activation rounding, reduceOnly |
| AC4 cancel_order | Pass | DELETE, id selection, dry-run default |
| AC5 test_order / `--exchange-test` | Pass (unit) | live smoke blocked by `-2015` from this host; rejected path exercised |
| AC6 guards | Pass with caveat | Should Fix 1 (missing `dualSidePosition` treated as one-way) |
| AC7 CLI + storage | Pass | rows verified in unit tests and real dry-run smoke |
| AC8 config/docs/tests | Pass | 247 tests OK, no network; Should Fix 2 on empty allowlist |

## Limitations

- No live or demo fill was attempted (agent policy); the exchange-side `/order/test` smoke returned `-2015` (IP/permission) so exchange validation of the parameter set remains unconfirmed from this environment.
- Source files changed on disk during review (coordinator's exchange_test change); the md5s above identify the reviewed state, and the suite was re-run afterwards.
- Lock contention was tested in-process via a holder thread (same flock file); cross-process contention not exercised.

VERDICT: PASS

## Iteration 2 (2026-09-20)

| Field | Value |
| --- | --- |
| Scope | Commits `3bd980d..bc454f4` on top of iteration 1 (PR #18, base 1b2a337): Algo Order API routing, unknown-outcome reconciliation, reduce-only/direction checks, CLI algo listing, cancel deactivation, `.env.example` |
| Reviewed state (md5 prefix) | `trading.py` 7f928f78, `client.py` f808aff7, `cli.py` 60c981d0, `storage.py` b5bc20f5, `test_binance_trading.py` 47a761e7, `test_cli.py` b06c0950 |
| Inputs | `git diff 1b2a337 -- kis_hl tests`, README, docs/architecture.md, skill SKILL.md + references/orders.md, `.env.example`; throwaway probes under `/tmp/qa2/` (not committed) |

### Commands and results

| Command | Result |
| --- | --- |
| `python3 -m unittest discover -s tests -t . -q` | `Ran 280 tests … OK`, exit 0 |
| `curl -s -o /dev/null -w '%{http_code}' https://fapi.binance.com/fapi/v1/{openAlgoOrders,algoOrder,openAlgoOrdersX}` (unauthenticated) | `401`, `401`, `404` — both algo routes exist |
| `/tmp/qa2/probe_unknown.py` (offline `send` stub) | Regex: HTTP 500/503/408, ` -1007/`, "An unknown error occurred" → unknown; 400 -2019, 429, 418, -1021, `HTTP 4080`, `-11007`, -2013 → rejected. POST lookup matrix: NEW/FILLED → `submitted/reconciled_after_unknown`; EXPIRED+executedQty 0.005 → `submitted/reconciled_partial_fill`; EXPIRED/CANCELED/EXPIRED_IN_MATCH with executedQty 0, missing, or garbage → `rejected/reconciled_terminal`; `{}`, list, lookup -2013 → `unknown`. Algo: NEW/TRIGGERED/FINISHED → submitted, EXPIRED → rejected. `URLError`/`TimeoutError`/`ConnectionResetError` → `unknown` (lookup also failing). DELETE unknown: lookup CANCELED → `submitted/reconciled_cancel`; NEW/FILLED/EXPIRED → `unknown`. Cancel-algo live: other symbol, list payload, `{}`, lookup 400 → `RuntimeError` with no DELETE sent; lowercase symbol accepted; ETHUSDT blocked by allowlist before lookup; dry-run makes zero calls. `close_position=True`+quantity → ValueError; `exchange_test` on algo → ValueError; SELL/BUY trailing activation on wrong side → ValueError; reduce-only LIMIT below notional → dry_run, non-reduce-only → ValueError; CONTRACT_PRICE stop calls `/fapi/v1/ticker/price` only |
| `/tmp/qa2/probe_storage.py` | `deactivate_protective_orders` with symbol+base_url+key_profile touched only the matching row ([1]); demo/production/ETHUSDT/inactive/other-id/hyperliquid rows untouched; idempotent ([]); client-id path scoped to demo row; no-id → ValueError; lowercase symbol normalised |
| `/tmp/qa2/smoke.py` (instrumented `send`, temp DB, mainnet public data, all dry-run) | 13 runs, only `GET fapi.binance.com /fapi/v1/{exchangeInfo,premiumIndex,ticker/price}`; **no `X-MBX-APIKEY` header and no `signature=` in any request** despite `.env` present. `binance-trade` limit 0.0021@60000.07 → `0.002`/`60000.00`, `POST /fapi/v1/order`; `binance-stop --kind stop-market --stop-price 50000.03` → `POST /fapi/v1/algoOrder` `algoType=CONDITIONAL triggerPrice=50000.10 closePosition=true` (no quantity/reduceOnly); with `--quantity 0.0015 --working-type CONTRACT_PRICE` → `quantity 0.001 reduceOnly true`; trailing `1.50`→`1.5`, `activatePrice 150000.00`; activation 1000 → exit 1 `must be above the mark price`; stop 999999 → exit 1; `--exchange-test` on stop → exit 1 `Algo Order API has no test endpoint`; `binance-cancel --algo-id/--client-algo-id` → `DELETE /fapi/v1/algoOrder`, zero network calls; stored rows: dry_run=1, protective `active=0 status=dry_run`; stored JSON contains no apikey/secret/signature words |
| `binance-cancel --algo-id 1 --client-algo-id x` | argparse exit 2 `not allowed with argument --algo-id` |
| `/tmp/qa2/probe_cli_state.py` (patched client) | `binance-stop` stores submitted+NEW / no `algoStatus` → active=1 `submitted`; FINISHED → active=0 `finished`; rejected/unknown/dry_run → active=0. `binance-cancel` dry_run/unknown/rejected → no deactivation; submitted on `key_profile=production` → `[]` (default row untouched); ack `algoId` differing from requested client id → `[]`; confirmed cancel → row 11 `active=0 canceled` |

### Findings

No Must Fix items.

**Should Fix**
1. Skill text contradicts the code on 5xx. `.agents/skills/binance-api/SKILL.md:143-145` says `503 "Service Unavailable" is a confirmed failure`, but `UNKNOWN_OUTCOME_RE` (`kis_hl/binance/trading.py:33`) treats every `HTTP 5xx` as unknown (probe: `HTTP 500 None/<html>` → unknown), which matches Binance's own guidance. `SKILL.md:100` also omits HTTP 408 / `-1007`, which `references/orders.md:68` lists. The skill is the owner for this knowledge; align it with the code.
2. Dead `--exchange-test` flag on `binance-stop`. `kis_hl/cli.py:345` advertises `Validate via /fapi/v1/order/test without placing`, but `_submit` (`trading.py:307-308`) always raises for the algo path; the flag can never succeed. Fails closed, so not blocking; remove it or reword the help to say algo orders have no test endpoint.

**Nit**
- `binance-cancel --order-id 5 --algo-id 6` silently ignores `--order-id` (`cli.py:913` `is_algo` wins); `binance-stop --kind trailing --stop-price` is likewise ignored. Consider rejecting mixed identifiers.
- `README.md:125` sample env still sets `BINANCE_TESTNET=false`, while `.env.example` now advises leaving it unset so the demo profile picks demo URLs; copying the README block with `BINANCE_KEY_PROFILE=demo` would point demo keys at mainnet.
- `rejected` and `unknown` submissions exit 0 (carried over from iteration 1); shell callers must parse `status`.
- An `unknown` `binance-stop` outcome is stored with `active=0 status=unknown` (conservative: operator sees the position as unprotected); worth one README sentence so it is not read as "not on the exchange".
- Deactivation by `client_request_id` marks every active row sharing that id; only reachable when an operator reuses `--client-order-id`.

### Verified behaviours (no issues)

Guard order unchanged: validation → dry-run return → allowlist → credentials → one-way mode (POST only) → `account_lock` → signed call; reconciliation lookups run inside the lock. Conditional orders carry `algoType`, `triggerPrice`/`activatePrice`, `clientAlgoId`; `closePosition` orders have neither quantity nor `reduceOnly`. Cancel-algo performs the symbol lookup only after allowlist and credential checks and refuses on any lookup failure or non-dict payload. `position_mode_is_hedge` now fails closed on a missing/non-boolean field, empty `BINANCE_LIVE_SYMBOLS` yields `()`, non-finite Decimals raise `ValueError`, `fullmatch` on client ids (iteration-1 Should Fix 1-3 and the newline nit resolved). `open_algo_orders` accepts list or `{"orders": []}` payloads; `binance-orders` falls back per symbol only on `-1102` and flags `open_algo_orders_complete=false`. Tests: all Binance trading/CLI tests use `example.test` hosts or `send` stubs raising `AssertionError`; no `urlopen`/socket use in `tests/`; real hostnames appear only as stored `base_url` literals. README, docs/architecture.md, orders.md, and the diagram match the code apart from the items above.

### AC verdicts

| AC | Verdict | Note |
| --- | --- | --- |
| AC1 place_order | Pass | reduce-only skips MIN_NOTIONAL; rounding and dry-run unchanged |
| AC2 place_stop_market | Pass | Algo Order API params; direction vs mark or last price; quantity/close_position exclusivity |
| AC3 place_trailing_stop | Pass | `activatePrice` direction validated; `reduceOnly=true` |
| AC4 cancel_order / cancel_algo_order | Pass | symbol lookup before algo cancel; unknown cancel reconciled |
| AC5 test_order / `--exchange-test` | Pass (unit) | algo path rejects the flag; live smoke still blocked by `-2015` from this host (iteration 1) |
| AC6 guards | Pass | hedge-mode guard fails closed; unknown outcomes never become `rejected` without a terminal lookup |
| AC7 CLI + storage | Pass | algo rows, inactive FINISHED, scoped deactivation verified by probes |
| AC8 config/docs/tests | Pass | 280 tests, no network; Should Fix 1 is doc drift in the skill |

### Limitations

- No live or demo order, cancel, or `binance-orders` call was made (agent policy); Algo Order API response shapes (`algoStatus` values, `executedQty` presence) are taken from documentation and tests, not observed.
- Cross-process lock contention and real 5xx/timeout behaviour were simulated with stubs only.
- Observation log for the task-observer skill was not written because this session's only permitted write target is this report.

VERDICT: PASS
