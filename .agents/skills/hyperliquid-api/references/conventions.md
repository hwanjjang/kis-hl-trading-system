# Notation, asset ids, tick and lot sizes

## Notation (v0 API, deliberately nonstandard)

| Abbrev | Meaning |
|---|---|
| `Px` | price |
| `Sz` | size, in units of the base coin |
| `Szi` | signed size — positive long, negative short |
| `Ntl` | notional, `Px * Sz` in USD |
| `Side` | `B` = bid = buy, `A` = ask = sell; for trades it is the aggressing side |
| `Asset` | integer id of the traded asset |
| `Tif` | time in force: `Gtc`, `Alo` (post-only), `Ioc` |
| `Oid` / `Cloid` | exchange order id / client order id |
| `tpsl` | `"tp"` take-profit or `"sl"` stop-loss on a trigger order |

## Asset ids

| Market | Asset id |
|---|---|
| Standard perp | index of the coin in `meta.universe` (BTC = 0) |
| Spot | `10000 + spotMeta.universe[i].index` |
| HIP-3 builder-deployed perp | `100000 + perp_dex_index * 10000 + index_in_meta` |

`perp_dex_index` is the position of the dex in the `perpDexs` response. Ids differ
between mainnet and testnet, and a spot pair's id is not its token id. Do not cache or
hardcode them — `hyperliquid-python-sdk` resolves names to ids at call time, which is
why this repo passes coin **names** everywhere.

## Coin naming by layer

| | info request | exchange order |
|---|---|---|
| Perp | `BTC` | `BTC` (SDK maps to id 0) |
| Spot | `UBTC/USDC` or `@<index>` | `@<index>` |
| HIP-3 perp | `xyz:XYZ100` | `xyz:XYZ100` |

`kis_hl/assets.py` normalizes user input: `BTCUSDC` / `BTC/USDC` → `UBTC/USDC` spot;
`BTC-PERP` / `BTCPERP` / `BTCUSDC-PERP` → `BTC` perp; `xyz:SYMBOL` or `dex=xyz` →
the mapped `hyperliquid_coin` from `trade_xyz_assets`, otherwise `xyz:<SYMBOL>`.
`resolve_spot_order_coin()` converts a spot pair to `@<index>` using `spotMeta`,
matching either `universe[].name` or the base/quote pair rebuilt from `tokens[]`.

## Tick and lot sizes

- Prices: at most **5 significant figures**, and at most `MAX_DECIMALS - szDecimals`
  decimal places. `MAX_DECIMALS` is **6 for perps** and **8 for spot**.
- Integer prices are always allowed regardless of significant figures.
- Sizes: rounded to the asset's `szDecimals` (from `meta` / `spotMeta`).
- Strip trailing zeroes before signing.

Perp examples: `1234.5` valid, `0.001234` valid, `1234.56` invalid (6 sig figs),
`0.0012345` invalid (7 decimals). With `szDecimals = 1`, `0.01234` is valid and
`0.012345` is not (more than 5 decimals allowed by `6 - 1`).

This repo stores `szDecimals` in the `xyz` universe snapshot table but does **not**
round order prices or sizes before sending. Any caller that computes a price
(ATR-derived stop, slippage-adjusted limit) must round it itself, or the exchange
returns `"Price must be divisible by tick size."`

## HIP-3 builder-deployed perps (the `xyz` dex)

- Coins are namespaced `{dex}:{coin}`; the dex has independent order books, margining,
  and deployer settings, and any approved quote asset can be the collateral token.
- Info calls target a dex with the `"dex"` field (`meta`, `metaAndAssetCtxs`, `allMids`,
  `clearinghouseState`, `openOrders`) or with the prefixed coin (`l2Book`,
  `candleSnapshot`). `dex: "ALL_DEXES"` aggregates clearinghouse state.
- The deployer sets an additional fee share (0–300%, 0–100% in growth mode) on top of
  protocol fees, and can call `haltTrading` to cancel all orders and settle positions at
  the mark price. Assume a trade.xyz market can be halted or resumed without notice.
- Per-dex caps exist (`perpDexLimits`: `totalOiCap`, `oiSzCapPerPerp`, `coinToOiCap`);
  `perpsAtOpenInterestCap` lists coins where OI-increasing orders are currently rejected.
- Hyperliquid itself does not enforce the underlying market's trading hours. That policy
  lives in this repo: `kis_hl/trading_hours.py` and `docs/trading_hours.md`.
