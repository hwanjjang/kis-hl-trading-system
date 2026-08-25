# KIS Open API: auth and transport

Source of truth: `examples_llm/kis_auth.py` in `koreainvestment/open-trading-api`
and `kis_hl/kis/client.py` in this repo.

## Hosts

| Purpose | Live | Paper |
|---|---|---|
| REST | `https://openapi.koreainvestment.com:9443` | `https://openapivts.koreainvestment.com:29443` |
| WebSocket | `ws://ops.koreainvestment.com:21000` (+ `/tryitout`) | `ws://ops.koreainvestment.com:31000` (+ `/tryitout`) |

Live and paper use **separate app keys**. A paper key cannot call the live host.

## Access token (REST)

```http
POST /oauth2/tokenP
content-type: application/json; charset=utf-8

{"grant_type":"client_credentials","appkey":"...","appsecret":"..."}
```

Response:

```json
{"access_token":"eyJ...","access_token_token_expired":"2026-08-27 06:31:12","token_type":"Bearer","expires_in":86400}
```

- Validity is 24 hours. Requesting again within a few hours returns the same token.
- Issuance is throttled by KIS (treat it as once per minute). Cache the token on disk;
  this repo stores `data/kis-tokens/kis-token-{sim|live}.json` with mode 0600 and
  refuses to re-issue within 60 seconds (`KisClient.get_access_token`).
- `POST /oauth2/revokeP` with `{"appkey","appsecret","token"}` revokes a token.

## WebSocket approval key

```http
POST /oauth2/Approval
{"grant_type":"client_credentials","appkey":"...","secretkey":"..."}
```

Field name is `secretkey` (not `appsecret`). Response `{"approval_key":"..."}`.
The key is sent in the WebSocket subscribe header, not as an HTTP header.

## Request headers for `/uapi/...`

| Header | Value |
|---|---|
| `content-type` | `application/json; charset=utf-8` |
| `authorization` | `Bearer <access_token>` |
| `appkey` / `appsecret` | app credentials |
| `tr_id` | transaction ID for the endpoint (see endpoints reference) |
| `custtype` | `P` personal, `B` partner/corporate |
| `tr_cont` | `""` first call, `N` to fetch the next page |
| `hashkey` | optional, for POST bodies (see below) |
| `personalseckey` | corporate accounts only |
| `User-Agent` | any browser-like UA (upstream sets one; not required by this repo) |

GET endpoints take query parameters; order/account POST endpoints take a JSON body.
Parameter names are upper-case (`FID_INPUT_ISCD`, `CANO`, `ORD_QTY`) and values are
strings, including numbers.

## Response shape

```json
{"rt_cd":"0","msg_cd":"MCA00000","msg1":"정상처리 되었습니다.","output":{...}}
```

- `rt_cd == "0"` means success. HTTP 200 with another `rt_cd` is an application error.
- Bodies use `output`, or `output1` (summary/single) + `output2` (list) for multi-part
  responses. Chart endpoints often return the newest row first.
- Response headers echo `tr_id` and carry `tr_cont`: `F`/`M` = more pages, `D`/`E` = last.

## Pagination

1. First call with header `tr_cont: ""` and empty `CTX_AREA_FK100` / `CTX_AREA_NK100`
   (names vary: `CTX_AREA_FK200`, `CTX_AREA_NK`, `KEYB` + `NEXT` for overseas minute bars).
2. If the response header `tr_cont` is `F` or `M`, call again with header `tr_cont: N`
   and the `ctx_area_*` values copied from the previous body.
3. Sleep between pages (upstream `smart_sleep`) and cap the loop (upstream `max_depth=10`).

## Hashkey (optional)

`POST /uapi/hashkey` with the same headers and the order body returns `{"HASH":"..."}`.
Put it in the `hashkey` header of the actual order request. KIS does not require it;
upstream samples call orders without it.

## Paper vs live TR IDs

Rule from `kis_auth._url_fetch`: when paper trading, a TR ID whose first letter is
`T`, `J`, or `C` becomes `V` + rest. Examples:

| API | Live | Paper |
|---|---|---|
| Domestic cash order buy | `TTTC0012U` | `VTTC0012U` |
| Domestic balance | `TTTC8434R` | `VTTC8434R` |
| Overseas balance | `TTTS3012R` | `VTTS3012R` |
| US buy order | `TTTT1002U` | `VTTT1002U` |
| US sell order | `TTTT1006U` | `VTTT1001U` (irregular!) |

Quote/market-data TR IDs (`FH…`, `HH…`) are unchanged. Not every endpoint exists on
paper; the upstream docstring for each endpoint states paper support.

## Rate limits

- Upstream sleeps 0.05s between calls on live and 0.5s on paper (`_smartSleep`), which
  matches the commonly documented 20 req/s (live) and 2 req/s (paper) limits.
- Exceeding it returns `msg_cd` `EGW00201` ("초당 거래건수를 초과하였습니다"), sometimes as
  HTTP 500. This repo detects both and retries with exponential backoff
  (`KisClient._request_with_auth`, `_is_rate_limited`).
- Token issuance has its own limit; never issue per request.

## Error codes seen in practice

| Code | Meaning | Action |
|---|---|---|
| `EGW00201` | too many requests per second | back off and retry |
| `EGW00123` | token expired | delete cache, re-issue once |
| `EGW00121` | invalid token / header | check `authorization`, key/host pairing |
| `EGW00133` | token issuance too frequent | wait ≥60s, reuse cached token |
| `OPSQ…`, `APBK…`, `40…` | endpoint-specific business errors (`msg1` explains) | validate params against the upstream sample |

Full list: KIS Developers portal → 고객센터 → 에러코드. Treat the codes above as
verified from client behavior and `msg1` text; confirm unfamiliar ones on the portal.

## Master data (symbol lists)

Symbol/exchange masters are downloadable `.mst` files, parsed by the upstream
`stocks_info/*.py` scripts (`kis_kospi_code_mst.py`, `overseas_stock_code.py`,
`overseas_index_code.py` → `frgn_code.mst`, `overseas_future_code.py` → `ffcode.mst`).
Use them when you need exact KIS symbols (e.g. `JP#NI225`, `.DJI`, futures roots).
