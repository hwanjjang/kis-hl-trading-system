# Hyperliquid WebSocket

`wss://api.hyperliquid.xyz/ws` (testnet: `wss://api.hyperliquid-testnet.xyz/ws`).
`kis_hl.hyperliquid.ws.default_hyperliquid_ws_url()` derives it from
`HYPERLIQUID_BASE_URL` when `HYPERLIQUID_WS_URL` is unset (`https` → `wss`, plus `/ws`).

## Envelope

```json
{"method": "subscribe",   "subscription": {"type": "allMids"}}
{"method": "unsubscribe", "subscription": {"type": "allMids"}}
```

Every server data frame is `{"channel": "<channel>", "data": ...}`. Subscribing also
produces a `{"channel": "subscriptionResponse", ...}` acknowledgement.

## Heartbeats

- The server closes a connection that has sent **no message for 60 seconds**.
- Client ping: `{"method": "ping"}` → server replies `{"channel": "pong"}`.
- This repo pings every 50s (`heartbeat_interval_ms=50_000` in
  `HyperliquidWebSocketClient.run()`) and treats a connection with no inbound message
  for `stale_after_ms` (default 15s) as stale, then reconnects with backoff
  (`MaintainedWebSocketClient` in `kis_hl/streaming.py`).

## Subscriptions

| `type` | fields | response channel |
|---|---|---|
| `allMids` | `[dex]` | `allMids` |
| `l2Book` | `coin`, `[nSigFigs]`, `[mantissa]`, `[fast]` | `l2Book` |
| `bbo` | `coin` | `bbo` |
| `trades` | `coin` | `trades` |
| `candle` | `coin`, `interval` | `candle` |
| `activeAssetCtx` | `coin` | `activeAssetCtx` |
| `activeAssetData` | `user`, `coin` | `activeAssetData` |
| `fastAssetCtxs` | – | `fastAssetCtxs` |
| `allDexsAssetCtxs` | – | `allDexsAssetCtxs` |
| `notification` | `user` | `notification` |
| `webData3` | `user` | `webData3` |
| `orderUpdates` | `user` | `orderUpdates` |
| `userEvents` | `user` | **`user`** |
| `userFills` | `user`, `[aggregateByTime]` | `userFills` |
| `userFundings` | `user` | `userFundings` |
| `userNonFundingLedgerUpdates` | `user` | `userNonFundingLedgerUpdates` |
| `userTwapSliceFills` / `userTwapHistory` | `user` | same name |
| `openOrders` | `user`, `dex` | `openOrders` |
| `clearinghouseState` | `user`, `dex` | `clearinghouseState` |
| `allDexsClearinghouseState` | `user` | `allDexsClearinghouseState` |
| `spotState` | `user`, `[isPortfolioMargin]` | `spotState` |
| `twapStates` | `user`, `dex` | `twapStates` |

Note the mismatch: `userEvents` answers on channel `"user"`. Match on the channel the
server sends, not the subscription name.

## Limits

Max 10 connections, 30 new connections per minute, 1000 subscriptions, 10 unique users
across user-specific subscriptions, 2000 outbound messages per minute, 100 simultaneous
in-flight post messages.

## Post requests over WebSocket

`{"method": "post", "id": <n>, "request": {"type": "info"|"action", "payload": {...}}}`
lets you run `/info` and `/exchange` calls over an open socket. This repo does not use
it; if you add it, keep the same dry-run and allowlist guards as the REST order path,
because `type: "action"` places real orders.

## Repo implementation

`kis_hl/hyperliquid/ws.py` builds subscriptions with
`all_mids_subscription(dex=)`, `user_fills_subscription(user)`,
`user_events_subscription(user)`, `all_dexs_clearinghouse_state_subscription(user)`, and
`candle_subscription(coin=, interval=)`, then runs them through
`HyperliquidWebSocketClient`. `parse_all_mids_ticks_payload()` filters on
`payload["channel"] == "allMids"` and converts `data.mids` into `PriceTick`s; it
silently skips values that are not parseable as `Decimal`.

Tests stub the transport (`tests/test_websocket_streams.py`); never open a real socket
in a test.
