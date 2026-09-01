# `/info` — public read endpoint

`POST https://api.hyperliquid.xyz/info`, header `Content-Type: application/json`,
body `{"type": "<type>", ...}`. No authentication. Testnet:
`https://api.hyperliquid-testnet.xyz/info`.

Conventions used below: `[x]` means optional. `user` must be the 42-char account
address, not an agent/API wallet. Spot coins are `PURR/USDC` or `@<index>`; HIP-3 perps
are `<dex>:<COIN>`.

## Perpetuals metadata and market data

| type | fields | response highlights |
|---|---|---|
| `meta` | `[dex]` | `universe[]` (`name`, `szDecimals`, `maxLeverage`), `marginTables` |
| `metaAndAssetCtxs` | `[dex]` | `[meta, assetCtxs[]]`; ctx has `funding`, `openInterest`, `dayNtlVlm`, `dayBaseVlm`, `midPx`, `markPx`, `oraclePx`, `prevDayPx` |
| `allPerpMetas` | – | meta + ctxs for every perp dex at once |
| `perpDexs` | – | `name`, `fullName`, `deployer`, `assetToStreamingOiCap`, `assetToFundingMultiplier`; index in this array feeds the asset-id formula |
| `perpDexLimits` | `dex` (required) | `totalOiCap`, `oiSzCapPerPerp`, `maxTransferNtl`, `coinToOiCap` |
| `perpDexStatus` | `dex` | `totalNetDeposit` |
| `perpsAtOpenInterestCap` | `[dex]` | coin names currently at OI cap — orders that increase OI are rejected |
| `fundingHistory` | `coin`, `startTime`, `[endTime]` | `fundingRate`, `premium`, `time` |
| `predictedFundings` | – | per-coin per-venue `fundingRate`, `nextFundingTime` |
| `perpDeployAuctionStatus` | – | `startTimeSeconds`, `durationSeconds`, `currentGas` |

`assetCtxs` is positionally aligned with `meta.universe`; zip by index, never by name
order alone. `kis_hl.xyz_market_collector` relies on this.

## Spot metadata and market data

| type | fields | response highlights |
|---|---|---|
| `spotMeta` | – | `tokens[]` (`name`, `szDecimals`, `weiDecimals`, `index`, `tokenId`, `isCanonical`), `universe[]` (`name`, `tokens` = `[baseIdx, quoteIdx]`, `index`, `isCanonical`) |
| `spotMetaAndAssetCtxs` | – | above plus `dayNtlVlm`, `markPx`, `midPx`, `prevDayPx` |
| `tokenDetails` | `tokenId` (34-char hex) | supply figures, `szDecimals`, `weiDecimals`, `midPx`, `markPx`, `genesis`, `deployer` |

Non-canonical pairs are named `@<index>` in `universe`. `UBTC/USDC` is canonical and
therefore has a real `name`, but the **exchange** still wants `@<index>`; see
`resolve_spot_order_coin` in `kis_hl/hyperliquid/client.py`.

## Order book, trades, candles

| type | fields | notes |
|---|---|---|
| `allMids` | `[dex]` | map coin → mid price string; falls back to last trade when the book is empty |
| `l2Book` | `coin`, `[nSigFigs]`, `[mantissa]` | 20 levels per side, each `{px, sz, n}`; `levels[0]` bids, `levels[1]` asks |
| `candleSnapshot` | `req: {coin, interval, startTime, endTime}` | up to 5000 candles; fields `t`, `T`, `s`, `i`, `o`, `c`, `h`, `l`, `v`, `n` |
| `recentTrades` | `coin` | weight scales with rows returned |

Candle intervals: `1m 3m 5m 15m 30m 1h 2h 4h 8h 12h 1d 3d 1w 1M`. `t` is the open
timestamp and `T` the close timestamp, both ms. A candle whose `T` is in the future is
still forming — the BTC 3H signal only uses closed candles.

## Account state

| type | fields | notes |
|---|---|---|
| `clearinghouseState` | `user`, `[dex]` | `assetPositions[]`, `marginSummary`, `crossMarginSummary`, `withdrawable`. `dex: "ALL_DEXES"` aggregates HIP-3 dexes |
| `spotClearinghouseState` | `user` | `balances[]` with `coin`, `token`, `hold`, `total`, `entryNtl` |
| `openOrders` | `user`, `[dex]` | resting orders: `coin`, `limitPx`, `oid`, `side`, `sz`, `timestamp` |
| `frontendOpenOrders` | `user`, `[dex]` | adds `orderType`, `triggerPx`, `isTrigger`, `tpsl`, `cloid` — use this to see stop orders |
| `historicalOrders` | `user` | up to 2000 recent orders with status |
| `orderStatus` | `user`, `oid` | one order: open / filled / canceled / rejected with reason |
| `userFills` | `user`, `[aggregateByTime]` | up to 2000 fills: `px`, `sz`, `fee`, `closedPnl`, `dir`, `hash` |
| `userFillsByTime` | `user`, `startTime`, `[endTime]`, `[aggregateByTime]` | paginate with the last `time` returned |
| `userFunding` | `user`, `startTime`, `[endTime]`, `[dex]` | `delta` = `{coin, fundingRate, usdc, szi}` |
| `userNonFundingLedgerUpdates` | `user`, `startTime`, `[endTime]`, `[dex]` | deposits, withdrawals, transfers |
| `activeAssetData` | `user`, `coin` | `leverage`, `maxTradeSzs`, `availableToTrade`, `markPx` — the cheapest pre-trade sizing check |
| `userFees` | `user` | fee schedule and daily volumes |
| `userRateLimit` | `user` | address-based request budget used / cap |
| `userRole` | `user` | `user` / `agent` / `vault` / `subAccount` / `missing` (weight 60) |
| `portfolio` | `user` | account value and PnL series |
| `subAccounts`, `userVaultEquities`, `vaultDetails` | see docs | not used by this repo |
| `approvedBuilders`, `maxBuilderFee` | `user`, (`builder`) | builder-fee state |
| `borrowLendUserState`, `borrowLendReserveState`, `allBorrowLendReserveStates` | – | lending markets, unused here |

Most history queries cap at 2000 rows. Paginate with the timestamp of the last row.

## Repo mapping

`kis_hl/hyperliquid/client.py` wraps `allMids`, `spotMeta`, `metaAndAssetCtxs`,
`l2Book`, `candleSnapshot`, `fundingHistory`, `clearinghouseState` (plain, spot, and
`ALL_DEXES`). Everything else in this table is unwrapped; follow the checklist in
`SKILL.md` section 5 before adding one.
