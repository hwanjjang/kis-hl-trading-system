# Test plan — binance-order-execution

| AC | Layer / scenario | Required | Expected | Failure | Test |
| --- | --- | --- | --- | --- | --- |
| AC1 | unit: round_to_step; MARKET dry-run request (qty rounded, newClientOrderId, respType); LIMIT requires price; price rounding by side; min notional / min qty / max qty rejections; live POST query + status submitted; HTTP error → rejected | yes | as spec | — | test_binance_trading |
| AC2 | unit: STOP_MARKET closePosition params (no quantity/reduceOnly); reduce-only variant; direction check vs mark | yes | as spec | — | test_binance_trading |
| AC3 | unit: TRAILING_STOP_MARKET params, callbackRate bounds/decimals, activation rounding | yes | as spec | — | test_binance_trading |
| AC4 | unit: cancel dry-run request; live DELETE query with orderId / origClientOrderId | yes | as spec | — | test_binance_trading |
| AC5 | unit: exchange_test posts to /order/test with signed params, status exchange_test, no lock/allowlist | yes | as spec | — | test_binance_trading |
| AC6 | unit: dry-run needs no creds; live: allowlist error before creds; creds error before position-mode call; hedge mode rejects before POST; lock acquired (real flock) | yes | ordered messages | — | test_binance_trading |
| AC7 | cli: binance-trade dry-run stores order_submissions row; binance-stop stores submission + protective row; binance-cancel stores row; output has no api_key | yes | rows | — | test_cli |
| AC8 | config: demo profile keys/urls; live symbols parsing; docs present; full suite green | yes | — | — | test_config + self-verification |
| smoke | real: `binance-trade` dry-run on mainnet public filters; `binance-stop --kind trailing` dry-run; `--exchange-test` with real keys (no placement) | yes | JSON, exchange test `{}` | — | self-verification |
