# `hyperliquid-python-sdk` and reading the docs

## Why the SDK is a dependency at all

Signed actions need EIP-712 typed-data signing over a `msgpack`-hashed action, plus
nonce handling and name→asset-id resolution. This repo deliberately delegates all of
that (`docs/architecture.md`: "Signed Hyperliquid actions use the SDK rather than
hand-written signatures"). Public reads use stdlib `urllib` instead, so the SDK is only
imported inside `HyperliquidTradingClient._load_sdk()` and a missing install fails with
a clear message rather than at import time.

```python
from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info

wallet = Account.from_key(private_key)
info = Info(base_url=base_url, skip_ws=True)
exchange = Exchange(wallet=wallet, base_url=base_url, account_address=account_address)
```

`skip_ws=True` matters: without it `Info` opens a websocket connection you never use and
that counts against the 10-connection limit.

## `Exchange` methods used here

```python
order(name, is_buy, sz, limit_px, order_type, reduce_only=False, cloid=None, builder=None)
market_open(name, is_buy, sz, px=None, slippage=DEFAULT_SLIPPAGE, cloid=None, builder=None)
```

`DEFAULT_SLIPPAGE = 0.05`. `market_open` fetches the mid and sends an aggressive IOC
limit at mid ± slippage; it is written for perps.

Other `Exchange` methods that exist but are intentionally unused:
`bulk_orders`, `modify_order`, `bulk_modify_orders_new`, `market_close`, `cancel`,
`cancel_by_cloid`, `bulk_cancel`, `schedule_cancel`, `update_leverage`,
`update_isolated_margin`, `usd_class_transfer`, `send_asset`, `sub_account_transfer`,
`vault_usd_transfer`, `usd_transfer`, `spot_transfer`, `withdraw_from_bridge`,
`approve_agent`, `approve_builder_fee`, `token_delegate`, the `spot_deploy_*` and
`perp_deploy_*` families, and validator actions. Each of these is a real signed action;
adding one is a trading-safety scope change under `AGENTS.md`.

## `Info` methods (alternative to this repo's info client)

`user_state(address, dex="")`, `spot_user_state`, `open_orders`, `frontend_open_orders`,
`all_mids(dex="")`, `user_fills`, `user_fills_by_time`, `meta(dex="")`,
`meta_and_asset_ctxs`, `perp_dexs`, `spot_meta`, `spot_meta_and_asset_ctxs`,
`funding_history`, `l2_snapshot`, `candles_snapshot`, `user_fees`, `query_order_by_oid`,
`query_order_by_cloid`, `historical_orders`, `portfolio`, `user_rate_limit`,
`user_role`, `name_to_asset`, `subscribe` / `unsubscribe`.

Prefer `HyperliquidInfoClient`. Reach for `Info` only when you need `name_to_asset`
(name → numeric asset id) or you are already inside the trading client.

## Reading the official docs

Base: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api

- Append `.md` to any page URL for clean markdown, e.g.
  `.../api/exchange-endpoint.md`.
- `https://hyperliquid.gitbook.io/hyperliquid-docs/llms.txt` is the full page index.
- `scripts/fetch_hl_docs.sh <page>` wraps both.

Page map used to build this skill:

| Page | Contents |
|---|---|
| `api/notation` | Px / Sz / Szi / Ntl / Side / Tif |
| `api/asset-ids` | perp, spot, and HIP-3 asset-id formulas |
| `api/tick-and-lot-size` | 5 sig figs, `MAX_DECIMALS - szDecimals` |
| `api/nonces-and-api-wallets` | nonce window, agent wallets |
| `api/info-endpoint` (+ `/perpetuals`, `/spot`) | every read request type |
| `api/exchange-endpoint` | every signed action, order schema, responses |
| `api/websocket` (+ `/subscriptions`, `/post-requests`, `/timeouts-and-heartbeats`) | realtime protocol |
| `api/error-responses` | rejection messages |
| `api/rate-limits-and-user-limits` | IP, address, and websocket limits |
| `api/signing` | EIP-712 details (only needed if the SDK is ever dropped) |
| `hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals` | the `xyz` dex model |

## Other SDKs

Rust `infinitefield/hypersdk`, TypeScript `nktkas/hyperliquid` and `nomeida/hyperliquid`,
and CCXT all cover the same API. They are useful as a second reading of an ambiguous
field, but this repo is Python-only.
