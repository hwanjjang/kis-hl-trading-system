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
Use `hyperliquid-python-sdk` for signing and action hashing. Normal actions use
its exchange helpers. The trailing adapter assembles the app-observed action and
envelope using the SDK's `sign_l1_action` and `Exchange.post`; do not implement
custom EIP-712 or msgpack signing.

## Native trailing stop

Official order types document perpetual trailing stops:
https://hyperliquid.gitbook.io/hyperliquid-docs/trading/order-types

The 2026-09-22 official app bundle `config-DWLPMyx3.js` constructs the following
separate action (`ace`), sends it through the normal signed exchange path
(`mce`, `I6`, `Uoe`, `ws`) and displays `Trailing Stop Market` orders:

```json
{"type":"trailingStop","asset":0,"isBuy":false,"sz":"1","reduceOnly":true,"retracement":{"px":"4"},"activationPx":null}
```

Field insertion order matters to the signed msgpack hash. Percentage retracement
uses `{"pct":"5.0000%"}`; price/size strings have no trailing zeros. Activation
is null for immediate activation or a price string. The action contains no cloid.
Public exchange docs and Python SDK 0.24.0 have no dedicated trailing helper;
the observed app contract is not a verified live response/acceptance guarantee.

`place_trailing_stop_order()` is dry-run by default, always reduce-only, validates
finite positive inputs, perp eligibility, verification freshness, direction/size,
lot/tick and expiry. Managed plans currently use quote distance rounded down from
frozen ATR using the distance's own significant figures and metadata decimal tick,
not the current quote's price grid. The supervisor persists the normalized distance
before entry and rejects zero; percentage and delayed activation are low-level
adapter options only.
Mark-price extrema are continuous and differ from the local nine-minute policy.

Query/cancel use ordinary `orderStatus` / `cancel` with the acknowledged native
oid. The app parses `triggerCondition` retracement/best/activation text (`s4`,
`l4`); our immediate quote-distance managed reader accepts only matching
quote retracement with immediate activation and a finite positive best price, or
waiting/omitted best. Known percentage and activation clauses are parsed but rejected
as managed-request semantic mismatches; unknown/duplicate clauses fail closed.
A submission acknowledgement or waiting readback is never active trailing coverage.
Missing oid, timeout or explicit rejection requires intervention, with no resend
or matching-based foreign adoption. This native submission intervention retains
fixed-SL monitoring and explicit exits. Verified open waiting orders do not cause
a timeout exit solely for waiting. Fixed native SL stays active; flat cleanup
includes both stop kinds. Do not recreate a previously accepted terminal trail
automatically because that resets its watermark; preserve residual-exit handling.

Evidence digest and investigation: `reports/sdlc/hyperliquid-native-trailing/`.
No live exchange orders were used to verify this integration.

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

## Other actions (cancel-by-oid is implemented; other actions are reference only)

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

`place_order()` reports per-order errors as `status="rejected"`; otherwise it
reports submission, never fill confirmation. Trailing attempts preserve raw
responses and require independent status/fill/position evidence before resending.

## SDK mapping used by this repo

| Repo call | SDK call | Resulting action |
|---|---|---|
| `place_order(order_type="market", reduce_only=False)` | `Exchange.market_open(coin, is_buy, sz, None, slippage)` | `order` with an IOC limit at mid ± slippage (default `0.05`) |
| `place_order(order_type="limit")` | `Exchange.order(coin, is_buy, sz, px, {"limit": {"tif": tif}}, reduce_only)` | `order`, `grouping: "na"` |
| `place_order(order_type="stop-market")` | `Exchange.order(coin, is_buy, sz, px, {"trigger": {...}}, True)` | reduce-only trigger order |
| `place_order(order_type="market", reduce_only=True)` | `Exchange.order(..., {"limit": {"tif": "Ioc"}}, True)` | Verified side, capped/rounded size and slippage-bounded price; perpetuals only |
| `place_order(..., cloid=...)` | Optional SDK `Cloid` on order/market_open | Reconciliation key; not an exactly-once guarantee |
| `cancel_order(symbol=..., oid=..., dry_run=True)` | `Exchange.cancel(coin, oid)` only when live | Guarded cancel by order ID; worker confirms terminal status |
| `user_state()` | `Info.user_state(address)` | `clearinghouseState` (read) |

`Exchange` is constructed with `wallet=Account.from_key(private_key)` and
`account_address=config.account_address`, which is the API-wallet pattern: the signer
may be an agent wallet, the account address is the funded account.

Full SDK method list: `sdk-and-docs.md`.

Local signed actions use an account lock; a running trailing worker holds it for its lifetime. Entry guards also inspect active live trailing state. Cancellation retains eligibility, metadata-freshness and credential checks. No modify or cancel-before-replace ratchet is implemented.

`place_order(expires_after_ms=...)` applies SDK `set_expires_after` for one action and resets it afterward. Trailing IOC attempts use receive-time plus the configured freshness budget; local preflight rejects expired prices and signed expiresAfter bounds delayed delivery. Expiry is not an exactly-once mechanism.
