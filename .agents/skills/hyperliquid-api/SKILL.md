---
name: hyperliquid-api
description: Hyperliquid API reference for this repo. Use when adding or debugging a Hyperliquid REST/WebSocket call in kis_hl/hyperliquid, looking up an /info request type or /exchange action, resolving a symbol to an L1 coin or asset id (spot @index, HIP-3 xyz: perps), sizing an order against tick/lot rules, or handling nonce, API-wallet, rate-limit, or order-rejection errors.
---

# Hyperliquid API

Use this skill for any work that touches Hyperliquid: `kis_hl/hyperliquid/client.py`,
`kis_hl/hyperliquid/ws.py`, `kis_hl/assets.py` symbol resolution, the `xyz` market
collectors, and the BTC strategy paths. Facts below were verified against the official
docs (`hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api`), the
`hyperliquid-python-sdk` source, and this repository's code.

## 0. Ground rules for this repo

- Public reads go through `kis_hl.hyperliquid.client.HyperliquidInfoClient`, which posts
  to `/info` with stdlib `urllib`. Do not add `requests` or call the SDK's `Info` class
  for a read the info client can do.
- Signed actions go through the official `hyperliquid-python-sdk` only
  (`HyperliquidTradingClient._load_sdk`). Never hand-write EIP-712 signing, nonces, or
  `msgpack` action hashing in this repo.
- Credentials come from `.env` via `kis_hl.config.load_hyperliquid_config()`. Never log
  or print `HYPERLIQUID_PRIVATEKEY`, and never commit `.env`.
- `place_order(dry_run=True)` is the default and must stay the default. Live paths fail
  closed: allowlist → trade.xyz verification freshness → credentials → session check.
  When you add a guard, add the rejecting test first.
- Adding a **new signed action** (cancel, modify, leverage, transfers, TWAP) is a scope
  change under `AGENTS.md` trading safety. It needs a dry-run default, an allowlist
  path, and tests before it is useful. Do not add one silently.
- Every new call needs a unit test in `tests/test_hyperliquid_client.py` or
  `tests/test_websocket_streams.py` with a stubbed transport. Tests never hit the network.

## 1. Environments

| | Mainnet | Testnet |
|---|---|---|
| REST base | `https://api.hyperliquid.xyz` | `https://api.hyperliquid-testnet.xyz` |
| WebSocket | `wss://api.hyperliquid.xyz/ws` | `wss://api.hyperliquid-testnet.xyz/ws` |
| Env keys | `HYPERLIQUID_BASE_URL`, `HYPERLIQUID_WS_URL` | same keys, testnet values |

Asset IDs and spot indices differ between mainnet and testnet. Never hardcode an index.

Wallet credentials: `HYPERLIQUID_WALLETADDRESS` (the account that holds the funds) and
`HYPERLIQUID_PRIVATEKEY` (ideally an approved API wallet, not the master key).
`HYPERLIQUID_KEY_PROFILE=production` switches to `PRO_HYPERLIQUID_*`.

## 2. Two endpoints, two trust levels

- `POST /info` — public, unauthenticated, `content-type: application/json`, body is
  `{"type": "...", ...}`. Everything this repo reads (mids, meta, books, candles,
  funding, account state) is here. No signature, no wallet needed, even for
  `clearinghouseState` of an arbitrary address.
- `POST /exchange` — signed. Body is `{"action", "nonce", "signature"}` plus optional
  `"vaultAddress"` and `"expiresAfter"`. `nonce` is a millisecond timestamp. The SDK
  signs this. Normal orders use `Exchange.order(...)` / `Exchange.market_open(...)`;
  native trailing uses the SDK's `sign_l1_action` and transport for the separate
  app-observed action (see `references/exchange-endpoint.md#native-trailing-stop`).

A wallet address in an info request must be the **actual account address**. Passing an
agent/API wallet address returns empty results, not an error.

Full type/action lists: `references/info-endpoint.md`, `references/exchange-endpoint.md`.

## 3. Symbol → coin → asset id (the thing to get wrong)

Three different names exist for the same market. Keep them straight:

| Layer | BTC spot | BTC perp | trade.xyz RWA |
|---|---|---|---|
| User/CLI symbol | `BTCUSDC` | `BTC-PERP` | `XYZ100`, `xyz:XYZ100` |
| L1 coin (info calls) | `UBTC/USDC` | `BTC` | `xyz:XYZ100` |
| Exchange order coin | `@<index>` from `spotMeta` | `BTC` | `xyz:XYZ100` |
| Asset id (raw API) | `10000 + spot index` | index in `meta.universe` | `100000 + dex_index*10000 + index_in_meta` |

- `kis_hl.assets.resolve_hyperliquid_symbol()` does the first two rows and returns a
  `ResolvedAsset(coin, kind, dex, note)`. Use it; do not re-parse symbols inline.
- `resolve_spot_order_coin(spot_meta, pair)` does the third row for spot, matching by
  `universe[].name` or by resolving the `tokens` index pair through `tokens[].name`.
- HIP-3 builder-deployed perps use `{dex}:{coin}` naming and are passed to info calls as
  a `"dex"` field (`meta`, `metaAndAssetCtxs`, `allMids`, `clearinghouseState`) or as the
  prefixed coin (`l2Book`, `candleSnapshot`). Each dex has its own order book,
  margining, and collateral token; `dex: "ALL_DEXES"` aggregates clearinghouse state.
- The repo never computes numeric asset ids: the SDK maps names for us. If you ever need
  one, read `references/conventions.md` instead of guessing.

## 4. What this repo already wraps

`HyperliquidInfoClient` (`kis_hl/hyperliquid/client.py`):

| Method | info `type` | Used by |
|---|---|---|
| `all_mids(dex=)` | `allMids` | `hl-mids`, `xyz-assets verify` |
| `spot_meta()` | `spotMeta` | spot `@index` resolution |
| `meta_and_asset_ctxs(dex=)` | `metaAndAssetCtxs` | `xyz-assets universe-collect` |
| `l2_book(symbol, dex=)` | `l2Book` | `xyz-assets spread-collect` |
| `candle_snapshot(...)` | `candleSnapshot` | `hl-candles`, BTC 3H signal, ATR(10D) |
| `funding_history(...)` | `fundingHistory` | `xyz-assets funding-collect` |
| `clearinghouse_state(user=, dex=)` | `clearinghouseState` | account state |
| `spot_clearinghouse_state(user=)` | `spotClearinghouseState` | spot balances |
| `all_dexs_clearinghouse_state(user=)` | `clearinghouseState` + `dex: ALL_DEXES` | HIP-3 totals |
| `account_asset_info(...)` | composite of the above | `hl-account` |
| `frontend_open_orders(...)` | `frontendOpenOrders` | trailing protection and ownership checks |
| `order_status(...)` | `orderStatus` by oid/cloid | trailing attempt and cleanup reconciliation |
| `user_fills_by_time(...)` | `userFillsByTime`, no aggregation | trailing / managed reconciliation and journal facts |
| `user_fills(...)` | `userFills`, no aggregation | Current retained-tail coverage anchor |
| `user_funding(...)` | `userFunding`, user/start/end | Actual account funding costs for deferred journals |

`HyperliquidTradingClient`: `place_order()`, `place_stop_loss_order()` (reduce-only
`trigger` with `isMarket: true`, `tpsl: "sl"`), `cancel_order()` (dry-run default), `user_state()`.
`place_order` forwards optional exchange cloid and distinguishes per-order rejection.
Signed actions share a local POSIX account lock; managed live coins reject new entries
until cleanup. Use the same verification/state database for all local commands.
`place_trailing_stop_order()` adds dry-run-first, reduce-only perpetual trailing.
It uses SDK asset IDs and L1 signing; the app-observed action has no cloid, so an
unknown result must never be resent or adopted by matching size/time.
`kis_hl/hyperliquid/ws.py`: `allMids`, `userFills`, `userEvents`,
`allDexsClearinghouseState`, `candle` subscriptions over `MaintainedWebSocketClient`.

## 5. Adding a new info call (checklist)

1. Confirm the request `type` and its exact field names in
   `references/info-endpoint.md`, or fetch the live page:
   `scripts/fetch_hl_docs.sh info-endpoint/perpetuals`.
2. Add a keyword-only method on `HyperliquidInfoClient` that builds the payload and
   calls `self.post_info(...)`. Validate the response shape and raise `RuntimeError`
   with the request name on mismatch, like the existing methods do.
3. Resolve any symbol argument through `resolve_hyperliquid_symbol()` and pass
   `resolved.coin`, never the raw user string.
4. Add a test in `tests/test_hyperliquid_client.py` with a recording subclass that
   overrides `post_info` and asserts the exact payload (see
   `test_account_asset_info_uses_public_wallet_state_endpoints`).
5. If it changes stored data, update the SQLite schema in `kis_hl/storage.py`, the
   collector, `docs/architecture.md`, and README.
6. Run `python3 -m unittest tests.test_hyperliquid_client tests.test_websocket_streams -q`.

To probe a live response shape before writing code (public data only):
`scripts/hl_info.sh '{"type":"metaAndAssetCtxs","dex":"xyz"}'`.

## 6. Order rules that reject after you send

These are enforced by the exchange, not by this repo. Get them wrong and the order is
rejected or silently ignored.

- **Tick size**: prices carry at most 5 significant figures **and** at most
  `MAX_DECIMALS - szDecimals` decimals, where `MAX_DECIMALS` is 6 for perps and 8 for
  spot. Integer prices are always legal. Violations return
  `"Price must be divisible by tick size."`
- **Lot size**: sizes are rounded to the asset's `szDecimals` from `meta` / `spotMeta`.
- **Exit rounding is scoped.** `prepare_perp_exit()` rounds size down and IOC prices
  inward to preserve slippage (sell up, buy down). Generic entries and initial trigger
  prices still need caller-side rounding; do not infer universal normalization.
- **Minimum notional** is $10 (`"Order must have minimum value of $10."`); the BTC
  strategy's 80 USDC tranche clears it, a partial add-up might not.
- **Reduce-only** orders that would increase a position are rejected
  (`"Reduce only order would increase position."`), so a stop-loss placed before the
  entry fills will fail.
- Non-reduce-only market orders use SDK `market_open` (IOC at mid ± slippage).
  Never use that helper for exits: it hardcodes reduce_only=False. Reduce-only
  perpetual market orders verify direction/size, then send a rounded fixed-side IOC
  through `Exchange.order(..., True)`. Spot reduce-only markets fail closed.
  Trailing management uses explicit reconciled-size IOC limit orders with cloids.
  SDK metadata includes base and xyz dexes; numeric asset IDs remain SDK-owned.

Full rejection list: `references/limits-and-errors.md`.

## 7. Rate limits

- Per IP: **1200 weight per minute**. Info weights: 2 for `l2Book`, `allMids`,
  `clearinghouseState`, `orderStatus`, `spotClearinghouseState`; 60 for `userRole`; 20
  for most others; history queries add weight per 20 rows returned, `candleSnapshot` per
  60 candles. Exchange actions weigh `1 + floor(batch_length / 40)`.
- Per address: 1 request per 1 USDC of cumulative volume, with a 10,000-request starting
  buffer. A batch of `n` orders is 1 IP request but `n` address requests.
- WebSocket: max 10 connections, 30 new connections/minute, 1000 subscriptions, 10
  unique users across user-specific subscriptions, 2000 outbound messages/minute.
- The collectors loop over the whole `xyz` universe. Keep their existing sleeps and do
  not add a second concurrent collector process against the same IP.

## 8. WebSocket

- Subscribe with `{"method": "subscribe", "subscription": {"type": ...}}`; unsubscribe
  with the same body and `"method": "unsubscribe"`.
- The server disconnects a connection that has sent nothing for 60 seconds. Send
  `{"method": "ping"}` and expect `{"channel": "pong"}`. This repo pings every 50s via
  `heartbeat_payload` in `HyperliquidWebSocketClient.run()`.
- Every data frame is `{"channel": ..., "data": ...}`. `userEvents` answers on channel
  `"user"`, not `"userEvents"` — check the channel name before parsing.
- Subscription list, fields, and channel names: `references/websocket.md`.

## 9. Reference files

- `references/info-endpoint.md` — every `/info` request type, fields, and response keys.
- `references/exchange-endpoint.md` — signed actions, order schema, tif/trigger/grouping, SDK mapping.
- `references/websocket.md` — subscriptions, channels, heartbeats, repo implementation.
- `references/conventions.md` — notation, asset ids, tick/lot sizes, spot `@index`, HIP-3 dexes.
- `references/limits-and-errors.md` — rate limits, nonces and API wallets, rejection messages.
- `references/sdk-and-docs.md` — `hyperliquid-python-sdk` surface and how to read the docs offline.
- `scripts/fetch_hl_docs.sh` — fetch any docs page as markdown, or ask it a question.
- `scripts/hl_info.sh` — POST a public `/info` request for shape checking (read-only).

Official docs: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api
Append `.md` to any docs URL for machine-readable markdown; `llms.txt` at the docs root
is the page index.

## Managed multi-instrument execution

Native BTC and ETH perpetuals are allowed; ETH-PERP/ETHUSDC-PERP resolve to ETH.
The account supervisor in `managed_execution.py` and `managed_gateways.py` is separate
from legacy single-position enrollment. It uses actual partial fills, strict native
Stop Market readback, local trailing by default, and durable client IDs for normal
orders. Explicit native trailing plans use continuous mark-price tracking after
terminal entry and fixed-SL coverage, retaining the fixed SL. Only the acknowledged
native order ID can establish trailing ownership; unknown outcomes require
intervention. Live trailing acceptance/execution is unverified. All trading CLIs must
use the same SQLite path. A managed owner blocks raw new entries and legacy
enrollment; only the in-process current entry attempt receives a submission permit.

Journal retention must be anchored by current `userFills`; a short old-window page
does not prove completeness. Unknown spot/fee-currency identities are retained
without finalizing performance. See [operations](../../../docs/trading-operations.md)
and the trade-journal skill for statement backfill and accounting.

## Canonical storage reads

`HyperliquidInfoClient.last_raw_body` exposes the most recent successful `/info`
response bytes for immutable evidence capture. It resets before each request.
Canonical collectors verify that these bytes match the decoded response before
using them; test/legacy decoded objects are labeled `decoded_json` instead.
`market backfill` supports native 1w/1d/1m candles. The API retains only the latest
5000 candles per interval; requested ten-year weekly coverage remains separate
from observed listing/provider history. Account funding identity includes coin,
time, interval/grain and hash; a zero hash alone is not an event identity.

The 2026-09-13 BTC native 1w probe returned Thursday UTC boundaries (for example,
2019-08-29 to 2019-09-05), not ISO Monday weeks. Canonical gap checks derive and
validate the anchor from returned timestamps; they do not re-label native candles
as derived ISO weeks. Reverify the actual interval if provider behavior changes.


Canonical public market collection currently accepts only the official mainnet
endpoint. Testnet/custom endpoints are rejected before collecting bars, quotes,
books or funding so they cannot replace a mainnet series. Account histories remain
separated by their existing environment/account identity. Old market observations
without verified endpoint provenance are not relabeled or certified by this guard.
