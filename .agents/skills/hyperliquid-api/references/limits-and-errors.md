# Rate limits, nonces, and error responses

## IP-based rate limits (REST)

Aggregated budget: **1200 weight per minute per IP**.

| Request | Weight |
|---|---|
| Exchange actions | `1 + floor(batch_length / 40)` |
| `l2Book`, `allMids`, `clearinghouseState`, `orderStatus`, `spotClearinghouseState`, `exchangeStatus` | 2 |
| `userRole` | 60 |
| All other documented info requests | 20 |
| `recentTrades`, `historicalOrders`, `userFills`, `userFillsByTime`, `fundingHistory`, `userFunding`, `nonUserFundingUpdates`, `twapHistory`, `userTwapSliceFills`, `userTwapSliceFillsByTime`, `delegatorHistory`, `delegatorRewards`, `validatorStats` | base + 1 per 20 rows returned |
| `candleSnapshot` | base + 1 per 60 candles returned |
| Explorer API | 40 (`blockList` also 1 per block) |

`xyz-assets universe-collect` / `funding-collect` / `spread-collect` iterate the whole
`xyz` universe, so they are the commands most likely to hit this. Keep their sleeps,
and do not run two collectors against the same IP at once.

## Address-based action limits

- 1 request per 1 USDC of cumulative traded volume, plus a starting buffer of 10,000
  requests. Cancels get `min(limit + 100000, limit * 2)`.
- Open order capacity: 1,000 base, +1 per 5M USDC volume, capped at 5,000.
- A batch of `n` orders counts as **1** IP request but **n** address requests.
- `reserveRequestWeight` buys additional address-based capacity. Check current usage
  with the `userRateLimit` info request.

## WebSocket limits

10 connections, 30 new connections per minute, 1000 subscriptions, 10 unique users
across user-specific subscriptions, 2000 outbound messages per minute, 100 simultaneous
in-flight post messages.

## Nonces and API wallets

- `nonce` is a millisecond timestamp and must fall inside `(T - 2 days, T + 1 day)`.
- Only the **100 highest nonces per signer** are retained; an older nonce is rejected.
- Nonces are tracked per signer: the account address when signing with the master key,
  or the agent address when signing with an API wallet.
- Use one API wallet per trading process. Sharing a wallet across processes causes nonce
  collisions that look like random rejections. After deregistering an agent, generate a
  new one rather than reusing the old address.
- API wallets are authorized with the `approveAgent` action. Info queries must still use
  the **account** address; querying an agent address returns empty data.
- In this repo, `HYPERLIQUID_PRIVATEKEY` is the signer and `HYPERLIQUID_WALLETADDRESS`
  is the account, wired as `Exchange(wallet=..., account_address=...)`. That is the
  API-wallet shape, so prefer an approved agent key over the master key in `.env`.

## Order rejection messages

| Error | Message |
|---|---|
| `Tick` | Price must be divisible by tick size. |
| `MinTradeNtl` | Order must have minimum value of $10. |
| `MinTradeSpotNtl` | Order must have minimum value of 10 {quote_token}. |
| `PerpMargin` | Insufficient margin to place order. |
| `ReduceOnly` | Reduce only order would increase position. |
| `BadAloPx` | Post only order would have immediately matched, bbo was {bbo}. |
| `IocCancel` | Order could not immediately match against any resting orders. |
| `BadTriggerPx` | Invalid TP/SL price. |
| `MarketOrderNoLiquidity` | No liquidity available for market order. |
| `PositionIncreaseAtOpenInterestCap` / `PositionFlipAtOpenInterestCap` | Order would increase open interest while open interest is capped |
| `TooAggressiveAtOpenInterestCap` | Order rejected due to price more aggressive than oracle while at open interest cap |
| `OpenInterestIncrease` | Order would increase open interest too quickly |
| `InsufficientSpotBalance` | (Spot-only) Order has insufficient spot balance to trade |
| `Oracle` | Order price too far from oracle |
| `PerpMaxPosition` | Order would cause position to exceed margin tier limit at current leverage |
| `MissingOrder` (cancel) | Order was never placed, already canceled, or filled. |

All of these arrive as HTTP 200 with `"status": "ok"` and the text inside
`response.data.statuses[].error`. See `exchange-endpoint.md` for the response shapes and
the unhandled-rejection gap in `place_order()`.

## Failure modes worth handling in this repo

- `HyperliquidInfoClient.post_info` raises `RuntimeError` on `HTTPError`, including the
  decoded body. HTTP 429 shows up there; treat it as backoff-and-retry, not as a bug.
- The `xyz` dex can be halted by its deployer (`haltTrading`), which cancels resting
  orders and settles positions at mark. A previously verified asset can therefore stop
  trading between the verification check and the order.
- `perpsAtOpenInterestCap` is not consulted anywhere in this repo; an OI-capped trade.xyz
  market will reject an entry that passes every local guard.
