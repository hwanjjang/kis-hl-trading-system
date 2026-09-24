# Binance USDⓈ-M futures WebSocket

## Market streams

Two roots, partitioned by stream tier (verified live 2026-09-16):

- `wss://fstream.binance.com/market` (demo `wss://demo-fstream.binance.com/market`) serves
  `markPrice`, `aggTrade`, `kline`, `forceOrder`, and other regular streams.
- `wss://fstream.binance.com/public` (demo `wss://demo-fstream.binance.com/public`) serves the
  high-frequency `bookTicker` and `depth` streams only.
- A subscription sent to the wrong root is accepted but never delivers frames; keep one tier
  per connection (`stream_route()`).

- Raw: `/ws/<stream>`; combined: `/stream?streams=<a>/<b>` → `{"stream": "<name>", "data": {...}}`.
- Symbols in stream names are lowercase. Connection valid 24 h, max 1024 streams, max 10
  inbound messages/s. Server ping every 3 min; reply pong within 10 min.
- Optional live subscribe: `{"method": "SUBSCRIBE", "params": ["btcusdt@bookTicker"], "id": 1}`.
  This repo does not use it; the URL form carries the subscription.

| Stream | Payload keys |
|---|---|
| `<s>@markPrice` (3 s) / `<s>@markPrice@1s` | `e=markPriceUpdate`, `E`, `s`, `p` mark, `i` index, `P` est. settle, `r` funding rate, `T` next funding |
| `<s>@bookTicker` | `e=bookTicker`, `u` update id, `s`, `b`/`B` bid/qty, `a`/`A` ask/qty, `T`, `E` |
| `<s>@kline_<interval>` | `e=kline`, `E`, `s`, `k{t,T,s,i,o,c,h,l,v,n,x closed,q,V,Q}` |
| `<s>@aggTrade` | `e=aggTrade`, `E`, `s`, `a` id, `p`, `q`, `f`, `l`, `T`, `m` buyer is maker |
| `<s>@depth<levels>@<speed>` | partial book | 
| `<s>@forceOrder` | liquidation orders |

`parse_market_ticks()` maps the first four into `PriceTick(source="binance")`: mark price,
bid/ask mid, kline close (+volume as size), agg trade price (+qty as size). `raw["kind"]` is
`mark_price`, `book_ticker`, `kline`, or `agg_trade`.

## User data stream

Base `wss://fstream.binance.com/private` (demo `wss://demo-fstream.binance.com/private`),
URL `/ws/<listenKey>`. Get the key from `POST /fapi/v1/listenKey`; valid 60 min; `PUT`
renews. `BinanceUserStreamClient` requests a key per connection (Binance may reuse the active account key), renews every 30 min on idle or message
ticks, and reconnects on `listenKeyExpired`.

### `ORDER_TRADE_UPDATE`

```json
{"e": "ORDER_TRADE_UPDATE", "E": 1568879465651, "T": 1568879465650,
 "o": {"s": "BTCUSDT", "c": "TEST", "S": "SELL", "o": "TRAILING_STOP_MARKET", "f": "GTC",
       "q": "0.001", "p": "0", "ap": "0", "sp": "7103.04", "x": "NEW", "X": "NEW", "i": 8886774,
       "l": "0", "z": "0", "L": "0", "N": "USDT", "n": "0", "T": 1568879465650, "t": 0,
       "b": "0", "a": "9.91", "m": false, "R": false, "wt": "CONTRACT_PRICE", "ot": "TRAILING_STOP_MARKET",
       "ps": "LONG", "cp": false, "AP": "7476.89", "cr": "5.0", "pP": false, "si": 0, "ss": 0, "rp": "0",
       "V": "EXPIRE_TAKER", "pm": "OPPONENT", "gtd": 0}}
```

| Key | Meaning | Key | Meaning |
|---|---|---|---|
| `s` | symbol | `c` | client order id |
| `S` | side BUY/SELL | `o` | order type |
| `f` | time in force | `q` | original quantity |
| `p` | original price | `ap` | average price |
| `sp` | stop price | `x` | execution type: NEW, CANCELED, CALCULATED (liquidation), EXPIRED, TRADE, AMENDMENT |
| `X` | order status: NEW, PARTIALLY_FILLED, FILLED, CANCELED, EXPIRED, EXPIRED_IN_MATCH | `i` | order id |
| `l` | last filled qty | `z` | cumulative filled qty |
| `L` | last filled price | `N` / `n` | commission asset / amount |
| `T` | trade time | `t` | trade id |
| `R` | reduce only | `wt` | working type MARK_PRICE / CONTRACT_PRICE |
| `ot` | original order type | `ps` | position side |
| `cp` | close-all (close position) | `AP` / `cr` | trailing activation price / callback rate |
| `rp` | realized profit of the trade | `V` | self-trade prevention mode |

Liquidation: `c` = `autoclose-...`; ADL: `c` = `adl_autoclose`.
`parse_order_event()` maps these to `OrderEvent` (Decimals, `reduce_only` bool) and
`order_event_to_row()` produces the `order_events` insert.

### Other events

- `ACCOUNT_UPDATE`: `a.m` reason (ORDER, FUNDING_FEE, DEPOSIT, WITHDRAW, MARGIN_TRANSFER,
  ADJUSTMENT, ...), `a.B[]` balances (`a` asset, `wb` wallet, `cw` cross wallet, `bc` change),
  `a.P[]` positions (`s`, `pa` amount, `ep` entry, `up` unrealized, `mt` margin type, `ps`).
- `MARGIN_CALL`: positions at risk.
- `listenKeyExpired`: no more events until a new key is used (not a socket close).
- `ALGO_UPDATE`: conditional-order lifecycle (NEW, TRIGGERING, TRIGGERED, FINISHED, CANCELED, REJECTED, EXPIRED).

The CLI counts non-order events under `other_events`; only `ORDER_TRADE_UPDATE` is stored.

Private streams tolerate data silence. Renewal retries are bounded to once per minute, with reconnect before key expiry. The runner does not DELETE shared account keys when disconnecting.
