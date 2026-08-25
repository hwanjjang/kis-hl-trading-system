# KIS endpoints: curated reference

Verified against `examples_llm/<category>/<folder>/<folder>.py` in
`koreainvestment/open-trading-api`. `tr_id` is a header. Paper IDs follow the
`T/J/C → V` rule unless listed. The full generated list is in
`endpoint-inventory.md`; use `scripts/find_kis_endpoint.sh` to open the sample.

## Domestic stock (국내주식) — quotes

| Upstream folder | Path | tr_id | Key params | Notes |
|---|---|---|---|---|
| `inquire_price` | `/uapi/domestic-stock/v1/quotations/inquire-price` | `FHKST01010100` | `FID_COND_MRKT_DIV_CODE=J`, `FID_INPUT_ISCD=005930` | Wrapped by `KisClient.inquire_domestic_price` |
| `inquire_ccnl` | `.../quotations/inquire-ccnl` | `FHKST01010300` | same | recent executions |
| `inquire_asking_price_exp_ccn` | `.../quotations/inquire-asking-price-exp-ccn` | `FHKST01010200` | same | order book + expected close |
| `inquire_daily_itemchartprice` | `.../quotations/inquire-daily-itemchartprice` | `FHKST03010100` | `FID_INPUT_DATE_1/2=YYYYMMDD`, `FID_PERIOD_DIV_CODE=D/W/M/Y`, `FID_ORG_ADJ_PRC=0` adj/`1` raw | max 100 rows per call; page by moving dates |
| `inquire_time_itemchartprice` | `.../quotations/inquire-time-itemchartprice` | `FHKST03010200` | `FID_INPUT_HOUR_1=HHMMSS`, `FID_PW_DATA_INCU_YN` | 1-minute bars, 30 per call |
| `inquire_daily_price` | `.../quotations/inquire-daily-price` | `FHKST01010400` | `FID_PERIOD_DIV_CODE`, `FID_ORG_ADJ_PRC` | 30 recent bars |
| `inquire_index_price` | `.../quotations/inquire-index-price` | `FHPUP02100000` | `FID_COND_MRKT_DIV_CODE=U`, `FID_INPUT_ISCD=2001` | KOSPI200 → wrapped as `inquire_domestic_index_price` |
| `inquire_daily_indexchartprice` | `.../quotations/inquire-daily-indexchartprice` | `FHKUP03500100` | `U`, index code, dates, period | index daily bars |
| `inquire_time_indexchartprice` | `.../quotations/inquire-time-indexchartprice` | `FHKUP03500200` | `U`, index code | index minute bars |
| `chk_holiday` | `.../quotations/chk-holiday` | `CTCA0903R` | `BASS_DT=YYYYMMDD` | paged with `CTX_AREA_FK/NK`; KRX trading calendar |
| `search_stock_info` | `.../quotations/search-stock-info` | `CTPF1002R` | `PRDT_TYPE_CD=300`, `PDNO` | listing date etc. |
| `inquire_vi_status` | `.../quotations/inquire-vi-status` | `FHPST01390000` | | volatility interruption |

Domestic index codes: `0001` KOSPI, `1001` KOSDAQ, `2001` KOSPI200, `0002` 대형주 ...
(portal FAQ "종목정보 다운로드(국내) - 업종코드").

## Domestic stock — account/orders (not wrapped in this repo)

| Folder | Path | Live tr_id | Paper | Notes |
|---|---|---|---|---|
| `order_cash` | `/uapi/domestic-stock/v1/trading/order-cash` | buy `TTTC0012U`, sell `TTTC0011U` | `VTTC0012U` / `VTTC0011U` | body `CANO, ACNT_PRDT_CD, PDNO, ORD_DVSN(00 limit, 01 market), ORD_QTY, ORD_UNPR, EXCG_ID_DVSN_CD=KRX` |
| `order_rvsecncl` | `.../trading/order-rvsecncl` | `TTTC0013U` | `VTTC0013U` | amend/cancel, needs `KRX_FWDG_ORD_ORGNO`, `ORGN_ODNO` |
| `inquire_balance` | `.../trading/inquire-balance` | `TTTC8434R` | `VTTC8434R` | `AFHR_FLPR_YN=N, INQR_DVSN=02, UNPR_DVSN=01, FUND_STTL_ICLD_YN=N, FNCG_AMT_AUTO_RDPT_YN=N, PRCS_DVSN=00` |
| `inquire_psbl_order` | `.../trading/inquire-psbl-order` | `TTTC8908R` | `VTTC8908R` | buying power |
| `inquire_daily_ccld` | `.../trading/inquire-daily-ccld` | `TTTC0081R` (≤3M) / `CTSC9215R` (older) | `VTTC0081R` | executions by date |

## Overseas stock (해외주식) — quotes (`/uapi/overseas-price/...`)

| Folder | Path | tr_id | Key params | Notes |
|---|---|---|---|---|
| `price` | `/uapi/overseas-price/v1/quotations/price` | `HHDFS00000300` | `AUTH=""`, `EXCD=NAS`, `SYMB=AAPL` | wrapped as `inquire_overseas_price`; delayed unless real-time entitlement |
| `price_detail` | `.../quotations/price-detail` | `HHDFS76200200` | same | adds 52w, PER, market cap |
| `dailyprice` | `.../quotations/dailyprice` | `HHDFS76240000` | `GUBN=0/1/2` (D/W/M), `BYMD=YYYYMMDD` or `""`, `MODP=0/1` | up to 100 bars ending at `BYMD`; page by moving `BYMD` |
| `inquire_daily_chartprice` | `.../quotations/inquire-daily-chartprice` | `FHKST03030100` | `FID_COND_MRKT_DIV_CODE=N` index / `X` FX / `I` bond / `S` gold; `FID_INPUT_ISCD=.DJI`, dates, `FID_PERIOD_DIV_CODE=D` | wrapped as `inquire_overseas_daily_chartprice`; US **stocks** here limited to DJI30/NDX100/SPX500 members |
| `inquire_time_indexchartprice` | `.../quotations/inquire-time-indexchartprice` | `FHKST03030200` | `N`/`X`/`KX`, `FID_INPUT_ISCD=SPX`, `FID_HOUR_CLS_CODE=0`, `FID_PW_DATA_INCU_YN=Y` | wrapped; used for `SP500`, `XYZ100` (`NDX`), `JP225` (`JP#NI225`) |
| `inquire_time_itemchartprice` | `.../quotations/inquire-time-itemchartprice` | `HHDFS76950200` | `EXCD, SYMB, NMIN=1..`, `PINC=1`, `NEXT=""/1`, `NREC≤120`, `KEYB=YYYYMMDDHHMMSS` | stock minute bars; daytime session codes `BAQ/BAY/BAA` |
| `inquire_asking_price` | `.../quotations/inquire-asking-price` | `HHDFS76200100` | `EXCD, SYMB` | top-of-book |
| `inquire_search` | `.../quotations/inquire-search` | `HHDFS76410000` | many `CO_*` filters | condition screener |
| `countries_holiday` | `/uapi/overseas-stock/v1/quotations/countries-holiday` | `CTOS5011R` | `TRAD_DT` | settlement/holiday calendar per country, paged |

Quote exchange codes (`EXCD`): `NAS` Nasdaq, `NYS` NYSE, `AMS` NYSE American/Arca ETFs,
`HKS` HK, `SHS` Shanghai, `SZS` Shenzhen, `TSE` Tokyo, `HNX` Hanoi, `HSX` Ho Chi Minh.
Overseas index symbols come from `frgn_code.mst` (e.g. `SPX`, `NDX`, `.DJI`, `JP#NI225`, `COMP`).

## Overseas stock — account/orders (not wrapped)

| Folder | Path | Live tr_id | Notes |
|---|---|---|---|
| `order` | `/uapi/overseas-stock/v1/trading/order` | US buy `TTTT1002U`, US sell `TTTT1006U`; HK `TTTS1002U`/`TTTS1001U`; SH `TTTS0202U`/`TTTS1005U`; SZ `TTTS0305U`/`TTTS0304U`; JP `TTTS0308U`/`TTTS0307U`; VN `TTTS0311U`/`TTTS0310U` | paper: US sell is `VTTT1001U` (not `VTTT1006U`); `OVRS_EXCG_CD` uses `NASD/NYSE/AMEX/...`; `ORD_DVSN` 00 limit, 31 MOO, 32 LOO, 33 MOC, 34 LOC; market orders still send `OVRS_ORD_UNPR="0"` |
| `daytime_order` | `.../trading/daytime-order` | `TTTS6036U` buy / `TTTS6037U` sell | US daytime (KST) session, limit only |
| `inquire_balance` | `.../trading/inquire-balance` | `TTTS3012R` | paper `VTTS3012R`; `OVRS_EXCG_CD`, `TR_CRCY_CD=USD` |
| `inquire_present_balance` | `.../trading/inquire-present-balance` | `CTRP6504R` | paper `VTRP6504R`; all currencies |
| `inquire_psamount` | `.../trading/inquire-psamount` | `TTTS3007R` | buyable quantity |

## Overseas futures/options (해외선물옵션)

| Folder | Path | tr_id | Notes |
|---|---|---|---|
| `inquire_price` | `/uapi/overseas-futureoption/v1/quotations/inquire-price` | `HHDFC55010000` | `SRS_CD=CLU26` style (root + month code + 2-digit year); roots from `ffcode.mst` |
| `daily_ccnl` | `.../quotations/daily-ccnl` | `HHDFC55020100` | daily bars by contract |
| `inquire_time_futurechartprice` | `.../quotations/inquire-time-futurechartprice` | `HHDFC55020400` | minute bars |
| `market_time` | `.../quotations/market-time` | dynamic | trading hours per exchange |
| `stock_detail` / `search_contract_detail` | `.../quotations/stock-detail` | `HHDFC55010100` | contract spec, tick size |

This repo keeps commodity (`WTIOIL`, `BRENTOIL`, `GOLD`, …) KIS rows `unsupported`
until front-month `SRS_CD` resolution from `ffcode.mst` is implemented. Do not hardcode
a contract month.

## Domestic futures/options, bonds, ETF/ETN, ELW

| Category | Example | Path | tr_id |
|---|---|---|---|
| domestic_futureoption | `inquire_price` | `/uapi/domestic-futureoption/v1/quotations/inquire-price` | `FHMIF10000000` |
| domestic_futureoption | `inquire_balance` | `.../trading/inquire-balance` | `CTFO6118R` / paper `VTFO6118R` |
| domestic_bond | `inquire_price` | `/uapi/domestic-bond/v1/quotations/inquire-price` | `FHKBJ773400C0` |
| etfetn | `inquire_price` | `/uapi/etfetn/v1/quotations/inquire-price` | `FHPST02400000` |
| etfetn | `nav_comparison_trend` | `/uapi/etfetn/v1/quotations/nav-comparison-trend` | `FHPST02440000` |
| elw | `udrl_asset_price` | `/uapi/elw/v1/quotations/udrl-asset-price` | `FHKEW154101C0` |

See `endpoint-inventory.md` for the remaining ~300 endpoints.

## Gotchas collected from the samples

- `inquire-daily-chartprice` for US stocks only covers DJI/NDX/SPX constituents; use
  `dailyprice` for any other US ticker.
- Overseas quote APIs (`HHDFS…`) accept `AUTH=""`; the field exists but is unused.
- Index minute-chart (`FHKST03030200`) returns the most recent bars only; there is no
  date parameter. For history use `inquire-daily-chartprice` with `N`.
- Domestic daily chart returns at most 100 rows; iterate with earlier `FID_INPUT_DATE_2`.
- Overseas prices are strings with the venue's decimals; convert with `Decimal`.
- Some endpoints need `custtype` and `tr_cont` even when they are empty strings.
- Paper trading rejects many analysis/ranking endpoints; the upstream docstring says
  "모의투자 미지원" when so.
