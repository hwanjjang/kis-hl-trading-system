# KIS WebSocket (실시간시세)

Source: `examples_llm/kis_auth.py` (`KISWebSocket`, `data_fetch`, `system_resp`,
`aes_cbc_base64_dec`) and this repo's `kis_hl/kis/ws.py`.

## Connect

- URL: `ws://ops.koreainvestment.com:21000/tryitout` (live) or
  `ws://ops.koreainvestment.com:31000/tryitout` (paper). `kis_hl.kis.ws` appends
  `/tryitout` if missing.
- Auth: obtain `approval_key` via `POST /oauth2/Approval` (see auth reference). No HTTP
  headers are needed on the socket itself.
- One connection can hold multiple subscriptions; KIS caps the number of
  simultaneously registered items (about 40 per approval key). Reuse one socket per
  process.

## Subscribe / unsubscribe message

```json
{
  "header": {"approval_key": "...", "custtype": "P", "tr_type": "1", "content-type": "utf-8"},
  "body": {"input": {"tr_id": "H0STCNT0", "tr_key": "005930"}}
}
```

- `tr_type`: `"1"` subscribe, `"2"` unsubscribe (upstream `KISWebSocket.unsubscribe`).
- `tr_key`: symbol (`005930`), for overseas `D` + exchange + symbol (e.g. `DNASAAPL`
  for delayed US, `RBAQAAPL` for real-time daytime), or HTS ID for execution notices.

## Message types

1. **JSON control messages** (`system_resp`):
   - Subscription ack: `body.rt_cd == "0"`, `body.msg1` `SUBSCRIBE SUCCESS` /
     `UNSUBSCRIBE SUCCESS`; `body.output.iv` and `body.output.key` are the AES
     parameters for encrypted feeds (notices).
   - `header.tr_id == "PINGPONG"`: echo the same text back to keep the connection alive.
2. **Data frames** (plain text): `0|H0STCNT0|001|f1^f2^...` — fields are
   `encrypted flag (0/1) | tr_id | record count | records`, records `^`-separated, and
   multiple records concatenated. Column order is documented in each upstream
   `examples_llm/<category>/<name>/<name>.py` (`columns` list). This repo decodes
   `H0STCNT0` and `HDFSCNT0` in `kis_hl.kis.ws.parse_kis_price_ticks`.
3. **Encrypted frames** (`1|...`): body is AES-256-CBC, base64; decrypt with the
   `key`/`iv` from the ack (`aes_cbc_base64_dec`). Used by execution notices
   (`H0STCNI0`, `H0GSCNI0`, ...).

## TR IDs (from upstream samples)

| Area | tr_id | Feed |
|---|---|---|
| Domestic stock KRX | `H0STCNT0` trades, `H0STASP0` order book, `H0STANC0` expected close, `H0STMKO0` market status, `H0STMBC0` member, `H0STPGM0` program trade, `H0STNAV0` ETF NAV, `H0STOUP0`/`H0STOAA0`/`H0STOAC0` after-hours |
| Domestic stock NXT | `H0NXCNT0`, `H0NXASP0`, `H0NXANC0`, `H0NXMKO0`, `H0NXMBC0`, `H0NXPGM0` |
| Domestic unified (KRX+NXT) | `H0UNCNT0`, `H0UNASP0`, `H0UNANC0`, `H0UNMKO0`, `H0UNMBC0`, `H0UNPGM0` |
| Domestic index | `H0UPCNT0` index trades, `H0UPANC0` expected, `H0UPPGM0` program |
| Domestic execution notice | `H0STCNI0` live, `H0STCNI9` paper (tr_key = HTS ID) |
| Domestic futures/options | `H0IFCNT0`/`H0IFASP0` index futures, `H0IOCNT0`/`H0IOASP0` index options, `H0ZFCNT0`/`H0ZFASP0` stock futures, `H0ZOCNT0`/`H0ZOASP0` stock options, `H0CFCNT0`/`H0CFASP0` commodity futures, `H0MFCNT0`/`H0MFASP0` night futures, `H0EUCNT0`/`H0EUASP0` night options, `H0IFCNI0` notice |
| Overseas stock | `HDFSCNT0` delayed trades, `HDFSASP0` order book, `HDFSASP1` delayed book (Asia), `H0GSCNI0` notice live / `H0GSCNI9` paper |
| Overseas futures/options | `HDFFF020` trades, `HDFFF010` book, `HDFFF1C0`/`HDFFF2C0` notices |
| Bonds | `H0BJCNT0` trades, `H0BJASP0` book, `H0BICNT0` bond index |
| ELW | `H0EWCNT0`, `H0EWASP0`, `H0EWANC0` |

## Operational notes

- Paper and live share the same websocket TR IDs except notices (`…CNI0` → `…CNI9`).
- If you see `No close frame received`, the HTS ID (`KIS_HTSID`) is usually wrong or missing.
- KIS drops idle sockets; reply to PINGPONG and use the reconnect/replay support in
  `kis_hl.streaming.MaintainedWebSocketClient`.
- Overseas real-time (non-delayed) US quotes require a paid entitlement; without it use
  `HDFSCNT0` delayed data or REST polling.
