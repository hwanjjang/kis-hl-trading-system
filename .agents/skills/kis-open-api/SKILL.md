---
name: kis-open-api
description: Korea Investment & Securities (KIS, 한국투자증권) Open API reference for this repo. Use when adding or debugging a KIS REST/WebSocket call in kis_hl/kis, looking up a KIS endpoint path or TR ID (tr_id), handling OAuth token / approval_key / rate-limit (EGW00201) errors, mapping a trade.xyz asset to a KIS quote route, or answering "how do I call KIS API X" for domestic/overseas stocks, indices, futures/options, bonds, ETF/ETN, ELW.
---

# KIS Open API

Use this skill for any work that touches the KIS Open API (한국투자증권 KIS Developers).
It is written for Claude Code and Codex. All facts below were verified against
`koreainvestment/open-trading-api` (`examples_llm/kis_auth.py` and the generated
endpoint samples) and this repository's `kis_hl/kis/client.py`.

## 0. Ground rules for this repo

- Reuse `kis_hl.kis.client.KisClient`. Do not vendor upstream `kis_auth.py` or add
  `requests`/`pandas`/`PyYAML` just to call one endpoint; the client uses stdlib `urllib`.
- Credentials come from `.env` via `kis_hl.config.load_kis_config()`. Never hardcode
  keys, never log `appkey`/`appsecret`/tokens, never commit `.env` or `data/kis-tokens/`.
- `SANDBOX=true` (default) selects paper-trading keys (`KIS_API_ST_*`) and the
  `openapivts` host. `SANDBOX=false` selects live keys (`KIS_API_*`).
- This repo uses KIS for **market data only**. Adding a KIS order endpoint is a scope
  change: it must be dry-run by default, fail closed, and follow `AGENTS.md`
  trading-safety rules. Do not add it silently.
- Every new endpoint needs a unit test in `tests/test_kis_client.py` (stub the
  transport; never hit the network in tests) and a README/docs note if it changes
  asset coverage or a mapping route.

## 1. Environments and endpoints

| | Live (실전) | Paper (모의) |
|---|---|---|
| REST base | `https://openapi.koreainvestment.com:9443` | `https://openapivts.koreainvestment.com:29443` |
| WebSocket | `ws://ops.koreainvestment.com:21000/tryitout` | `ws://ops.koreainvestment.com:31000/tryitout` |
| Env keys | `KIS_API_KEY`, `KIS_API_SECRET`, `KIS_STOCK_ACCOUNT` | `KIS_API_ST_KEY`, `KIS_API_ST_SECRET`, `KIS_ST_STOCK_ACCOUNT` |

Account numbers are 10 digits: `CANO` (first 8) + `ACNT_PRDT_CD` (last 2; `01`
brokerage, `03` domestic F&O, `08` overseas F&O, `22`/`29` pension).
`kis_hl.config.normalize_kis_account()` splits them.

## 2. Auth in one screen

- `POST /oauth2/tokenP` body `{"grant_type":"client_credentials","appkey","appsecret"}`
  → `access_token`, `access_token_token_expired` (`"YYYY-MM-DD HH:MM:SS"`, KST).
  Token lives ~24h. KIS throttles issuance (about once per minute; re-issuing
  within a few hours returns the same token). `KisClient.get_access_token()` caches
  it on disk (`KIS_TOKEN_DIR`, mode 0600) and refuses to re-issue within 60s.
- `POST /oauth2/Approval` body `{"grant_type":"client_credentials","appkey","secretkey"}`
  (note **`secretkey`**, not `appsecret`) → `approval_key` for WebSocket.
- `POST /uapi/hashkey` is optional integrity hashing for POST bodies; upstream samples
  skip it. Not needed for GET market-data calls.
- Per-request headers: `content-type: application/json; charset=utf-8`,
  `authorization: Bearer <token>`, `appkey`, `appsecret`, `tr_id`, `custtype: P`
  (`B` for partner firms), `tr_cont` (`""` first page, `"N"` next page).
- Response body: `rt_cd` (`"0"` = success), `msg_cd`, `msg1`, then `output` /
  `output1` / `output2`. HTTP 200 with `rt_cd != "0"` is still an error.

Details, pagination, hashkey and error codes: `references/auth-and-transport.md`.

## 3. TR ID rules you must not get wrong

- The TR ID goes in the `tr_id` **header**, not the query string.
- Paper trading uses a different TR ID only for account/order APIs: if the live ID
  starts with `T`, `J`, or `C`, replace the first letter with `V` (`TTTC8434R` →
  `VTTC8434R`). Quote APIs (`FH…`, `HH…`, `CT…` quotations) are the same in both.
- WebSocket TR IDs are identical across environments except execution notices
  (`H0STCNI0` live → `H0STCNI9` paper).
- Some endpoints choose the TR ID by parameter (buy vs sell, exchange, market).
  Always read the upstream sample; see `references/endpoints.md`.

## 4. Endpoints this repo already wraps (`kis_hl/kis/client.py`)

| Method | Path | tr_id | Used for |
|---|---|---|---|
| `inquire_domestic_price` | `/uapi/domestic-stock/v1/quotations/inquire-price` | `FHKST01010100` | KR stocks (`FID_COND_MRKT_DIV_CODE=J`) |
| `inquire_domestic_index_price` | `/uapi/domestic-stock/v1/quotations/inquire-index-price` | `FHPUP02100000` | `KR200` → `U` / `2001` |
| `inquire_overseas_price` | `/uapi/overseas-price/v1/quotations/price` | `HHDFS00000300` | US stocks/ETFs (`EXCD` NAS/NYS/AMS) |
| `inquire_overseas_time_indexchartprice` | `/uapi/overseas-price/v1/quotations/inquire-time-indexchartprice` | `FHKST03030200` | `SP500`→`SPX`, `XYZ100`→`NDX`, `JP225`→`JP#NI225` |
| `inquire_overseas_daily_chartprice` | `/uapi/overseas-price/v1/quotations/inquire-daily-chartprice` | `FHKST03030100` | Index/FX daily bars (`N`/`X`) |
| `get_websocket_approval_key` | `/oauth2/Approval` | – | WebSocket auth |

Routes from trade.xyz assets to these methods live in `kis_hl/kis_mappings.py`;
commodity and FX rows are intentionally `unsupported` until a front-contract
resolver exists (see `docs/architecture.md` "Open Risks").

## 5. Adding a new KIS endpoint (checklist)

1. Find the upstream sample: `scripts/find_kis_endpoint.sh <keyword>` (clones
   `open-trading-api` shallowly into `${KIS_UPSTREAM_DIR:-/tmp/kis-open-trading-api}`
   and greps `examples_llm/`). Read `<category>/<endpoint>/<endpoint>.py`: it has the
   `API_URL`, `tr_id` selection logic, param names, and example values.
2. Add a keyword-only method to `KisClient` that calls `self._request_with_auth(...)`
   with the exact upper-case param names KIS expects. Keep the wrapper thin: no
   pandas, no retries beyond what `_request_with_auth` already does.
3. If the response is paged (`tr_cont` header `F`/`M`), loop with `tr_cont="N"` and
   the `CTX_AREA_FK*`/`CTX_AREA_NK*` values from the previous body; cap iterations.
4. Test with a fake transport in `tests/test_kis_client.py`: assert path, `tr_id`
   header, query params, and paper/live TR ID switching if applicable.
5. If the endpoint backs a trade.xyz asset, add the route in `kis_mappings.py`,
   extend `tests/test_kis_mappings.py`, and update README + `docs/trade_xyz_assets.md`.
6. Run `python -m pytest tests/test_kis_client.py tests/test_kis_mappings.py -q`.

## 6. Common parameter codes

- Domestic market (`FID_COND_MRKT_DIV_CODE`): `J` KRX, `NX` NXT, `UN` unified;
  `U` for indices (`0001` KOSPI, `1001` KOSDAQ, `2001` KOSPI200).
- Overseas quote exchange (`EXCD`): `NAS` `NYS` `AMS` `HKS` `SHS` `SZS` `TSE` `HNX`
  `HSX`; daytime session `BAQ` `BAY` `BAA`.
- Overseas order exchange (`OVRS_EXCG_CD`): `NASD` `NYSE` `AMEX` `SEHK` `SHAA` `SZAA`
  `TKSE` `HASE` `VNSE` (different vocabulary from quotes!).
- Overseas index/FX chart market: `N` index, `X` FX, `I` bonds, `S` gold futures.
- Period (`FID_PERIOD_DIV_CODE` / `GUBN`): `D`/`0` day, `W`/`1` week, `M`/`2` month, `Y` year.
- Dates are `YYYYMMDD` strings; prices/quantities are strings in request bodies.

## 7. Rate limits and errors

- Upstream sample sleeps 0.05s between calls on live and 0.5s on paper; the commonly
  documented ceilings are 20 req/s live and 2 req/s paper. This repo throttles with
  `KIS_MIN_REQUEST_INTERVAL_MS` (default 300) and retries `EGW00201`
  ("초당 거래건수 초과") with backoff (`KIS_RATE_LIMIT_RETRIES`, `KIS_RATE_LIMIT_DELAY_MS`).
- 401/403 or token-expiry codes (`EGW00123`) → the client deletes the cached token and
  retries once. Do not loop token issuance; KIS limits it.
- Paper accounts do not support every endpoint (e.g. many analysis/ranking APIs,
  some order types). If a paper call returns an "unsupported" message, verify against
  the portal before assuming a bug.

## 8. WebSocket

Subscribe payload, PINGPONG echo, AES decryption for notices, and the TR ID list are
in `references/websocket.md`. This repo's implementation is `kis_hl/kis/ws.py`
(`H0STCNT0` domestic trades, `HDFSCNT0` overseas delayed trades).

## 9. Reference files

- `references/auth-and-transport.md` — headers, token lifecycle, pagination, hashkey, errors.
- `references/endpoints.md` — curated endpoints with live/paper TR IDs and gotchas.
- `references/endpoint-inventory.md` — generated table of all 333 upstream samples (path + TR IDs).
- `references/websocket.md` — realtime protocol and TR IDs.
- `references/upstream-repo.md` — layout of `open-trading-api`, official MCP servers, `kis-ai-extensions`.
- `scripts/find_kis_endpoint.sh` — local keyword search over upstream samples.

Official docs: https://apiportal.koreainvestment.com (API 문서, 에러코드, 종목정보 다운로드).
The portal is a JS app; when offline, the upstream GitHub samples are the most
reliable machine-readable spec.
