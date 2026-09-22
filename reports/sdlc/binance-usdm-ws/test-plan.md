# Test plan — binance-usdm-ws

| AC | Layer / scenario | Required | Expected | Failure | Test |
| --- | --- | --- | --- | --- | --- |
| AC1 | unit config: default/profile/testnet/override/bad profile | yes | correct urls/keys; RuntimeError on bad profile | wrong selection | tests/test_config.py::BinanceConfigTests |
| AC1 | unit client: signed call without creds | yes | RuntimeError before transport | network attempted | test_binance_client |
| AC2 | unit client: sign_query known vector; signed GET query order + header; public GET no header; listenKey POST/PUT/DELETE header only | yes | exact url/headers recorded | mismatch | test_binance_client |
| AC2 | unit client: symbol_filters normalization; klines normalization; invalid interval ValueError; HTTP error surfaces code/msg | yes | as spec | — | test_binance_client |
| AC3 | unit ws: stream names lowercase; combined url; parse markPrice/bookTicker/kline/aggTrade (raw + combined envelope); junk skipped | yes | PriceTick list | — | test_binance_ws |
| AC3 | unit cli: binance-stream stores ticks via fake transport | yes | rows in market_ticks source=binance | — | test_cli |
| AC4 | unit ws: user client creates listenKey per connection, keepalive on idle when due, listenKeyExpired -> reconnect with new key, parse ORDER_TRADE_UPDATE | yes | counters/keys as expected | — | test_binance_ws |
| AC4 | unit storage: store/list order_events | yes | roundtrip | — | test_storage_order_events |
| AC4 | unit cli: binance-user-stream stores events; binance-order-events lists | yes | JSON | — | test_cli |
| AC5 | unit cli: binance-info/mark/candles/orders with patched client | yes | JSON, no secret keys | — | test_cli |
| AC6 | content check: symlink resolves; docs mention commands | yes | files exist | — | manual check in self-verification |
| AC7 | full suite + public smoke | yes | exit 0 | — | self-verification |
