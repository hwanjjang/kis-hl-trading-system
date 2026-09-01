# `/exchange` — signed actions

`POST https://api.hyperliquid.xyz/exchange` with body:

```json
{
  "action": { "type": "...", "...": "..." },
  "nonce": 1699999999999,
  "signature": { "r": "0x...", "s": "0x...", "v": 27 },
  "vaultAddress": "0x...",
  "expiresAfter": 1699999999999
}
```

`nonce` is a millisecond timestamp. `vaultAddress` and `expiresAfter` are optional.
In this repo the whole envelope is built and signed by `hyperliquid-python-sdk`; never
construct it by hand.

## Order action

```json
{
  "type": "order",
  "orders": [
    {
      "a": 0,
      "b": true,
      "p": "29792.0",
      "s": "0.0147",
      "r": false,
      "t": { "limit": { "tif": "Gtc" } },
      "c": "0x1234...cdef"
    }
  ],
  "grouping": "na"
}
```

| Field | Meaning |
|---|---|
| `a` | asset id (integer; see `conventions.md`) |
| `b` | isBuy |
| `p` | limit price (string). For a market order the SDK sends an aggressive IOC price, not a zero |
| `s` | size in base units (string) |
| `r` | reduceOnly |
| `t` | order type: `{"limit": {...}}` or `{"trigger": {...}}` |
| `c` | cloid, optional 128-bit hex client order id |

- `tif`: `"Gtc"` good-til-cancel, `"Ioc"` immediate-or-cancel, `"Alo"` post-only.
- Trigger orders: `{"trigger": {"isMarket": bool, "triggerPx": "string", "tpsl": "tp"|"sl"}}`.
  A stop-loss is `tpsl: "sl"` with `r: true`. This repo's `place_stop_loss_order()`
  produces exactly that, with `isMarket: true`.
- `grouping`: `"na"`, `"normalTpsl"`, or `"positionTpsl"`. Use a group only when the
  entry and its TP/SL are sent in one `orders` array; the repo currently sends them
  separately with `"na"`.

## Other actions (reference only — none are implemented here)

| Action | Required fields | Purpose |
|---|---|---|
| `cancel` | `cancels[]` of `{a, o}` | cancel by order id |
| `cancelByCloid` | `cancels[]` of `{asset, cloid}` | cancel by client order id |
| `modify` | `oid` or `cloid`, `order` | amend one order |
| `batchModify` | `modifies[]` | amend many |
| `scheduleCancel` | `[time]` | dead-man's switch |
| `twapOrder` / `twapCancel` | `twap {a,b,s,r,m,t}` / `{a,t}` | TWAP execution |
| `updateLeverage` | `asset`, `isCross`, `leverage` | leverage mode and multiple |
| `updateIsolatedMargin` | `asset`, `isBuy`, `ntli` | add/remove isolated margin |
| `usdClassTransfer` | `amount`, `toPerp` | move USDC spot ↔ perp |
| `sendAsset` | `destination`, `sourceDex`, `destinationDex`, `token`, `amount` | move collateral between HIP-3 dexes |
| `usdSend`, `spotSend`, `withdraw3` | `destination`, `amount`, `time` (+`token`) | transfers and bridge withdrawal |
| `approveAgent` | `agentAddress`, `agentName` | authorize an API wallet |
| `approveBuilderFee` | `builder`, `maxFeeRate` | builder fee ceiling |
| `vaultTransfer`, `cDeposit`, `cWithdraw`, `tokenDelegate` | see docs | vaults and staking |
| `reserveRequestWeight` | `weight` | buy extra address-based rate limit |
| `noop` | – | burn a nonce to invalidate in-flight orders |

Anything that moves funds (`usdSend`, `spotSend`, `withdraw3`, `sendAsset`,
`vaultTransfer`) is out of scope for this repo. Do not add it as a convenience.

## Responses: HTTP 200 does not mean filled

```json
{"status":"ok","response":{"type":"order","data":{"statuses":[{"resting":{"oid":77738308}}]}}}
{"status":"ok","response":{"type":"order","data":{"statuses":[{"filled":{"totalSz":"0.02","avgPx":"1891.4","oid":77747314}}]}}}
{"status":"ok","response":{"type":"order","data":{"statuses":[{"error":"Order must have minimum value of $10."}]}}}
{"status":"ok","response":{"type":"cancel","data":{"statuses":["success"]}}}
```

A **rejected order still returns `"status": "ok"`** with the reason inside
`response.data.statuses[].error`. Per-order status is positional: `statuses[i]`
corresponds to `orders[i]`.

**Open gap in this repo**: `HyperliquidTradingClient.place_order()` returns
`OrderSubmission(status="submitted")` and logs `hyperliquid_order_submitted` without
inspecting `statuses[].error`. `extract_hyperliquid_order_id()` returns `None` for a
rejected order, which is the only current signal. If you touch this path, add an
explicit rejection check plus a test before adding anything else.

## SDK mapping used by this repo

| Repo call | SDK call | Resulting action |
|---|---|---|
| `place_order(order_type="market")` | `Exchange.market_open(coin, is_buy, sz, None, slippage)` | `order` with an IOC limit at mid ± slippage (default `0.05`) |
| `place_order(order_type="limit")` | `Exchange.order(coin, is_buy, sz, px, {"limit": {"tif": tif}}, reduce_only)` | `order`, `grouping: "na"` |
| `place_order(order_type="stop-market")` | `Exchange.order(coin, is_buy, sz, px, {"trigger": {...}}, True)` | reduce-only trigger order |
| `user_state()` | `Info.user_state(address)` | `clearinghouseState` (read) |

`Exchange` is constructed with `wallet=Account.from_key(private_key)` and
`account_address=config.account_address`, which is the API-wallet pattern: the signer
may be an agent wallet, the account address is the funded account.

Full SDK method list: `sdk-and-docs.md`.
