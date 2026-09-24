# Binance USDⓈ-M futures limits and errors

## Rate limits

| Limit | Value | Header |
|---|---|---|
| REQUEST_WEIGHT per IP | 2400 / minute | `x-mbx-used-weight-1m` |
| ORDERS per account | 300 / 10 s, 1200 / minute | `x-mbx-order-count-10s`, `x-mbx-order-count-1m` |
| WebSocket | 24 h per connection, 1024 streams, 10 inbound msgs/s, 300 connections per 5 min per IP | – |

HTTP 429: limit exceeded, back off (respect `Retry-After`). HTTP 418: IP banned after
repeated 429s, from 2 minutes up to 3 days. HTTP 403: WAF block. HTTP 5xx: Binance side;
503 `"Unknown error"` = request may have executed (verify first), 503 `"Service Unavailable"` =
confirmed failure.

## Error codes seen on read and stream paths

| Code | Meaning | Action |
|---|---|---|
| -1000 | unknown | retry with backoff |
| -1003 | too many requests | back off; check weight header |
| -1008 | server overloaded | reduce-only / close orders are exempt |
| -1021 | timestamp outside recvWindow | sync clock; compare with `/fapi/v1/time` |
| -1022 | invalid signature | query string mismatch; check param order and secret profile |
| -1102 / -1104 | mandatory param missing / unread params | fix params |
| -1120 | invalid interval | use a listed kline interval (no `3h`) |
| -1121 | invalid symbol | check `exchangeInfo` |
| -2014 / -2015 | bad API key format / invalid key, IP, or permissions | verify key, IP whitelist, futures permission |

## Order-path codes (for the future order iteration)

| Code | Meaning |
|---|---|
| -2010 | new order rejected |
| -2011 | cancel rejected |
| -2013 | order does not exist |
| -2018 / -2019 | balance / margin insufficient |
| -2021 | order would immediately trigger |
| -2022 | reduce-only rejected |
| -4003 / -4004 / -4005 | negative quantity / quantity below minimum / quantity above maximum |
| -4013 / -4014 | price below minimum / not multiple of tick size |
| -4023 | quantity not a multiple of step size |
| -4028 | leverage not valid |
| -4131 | counterparty best price does not meet PERCENT_PRICE |
| -4164 | order notional below MIN_NOTIONAL |
