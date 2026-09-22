# Managed account and cash-order routes

Verified against the official
[KIS examples](https://github.com/koreainvestment/open-trading-api/tree/main/examples_llm)
on 2026-09-12. Exact query construction lives in `kis_hl/kis/routes.py`.

| Account inquiry | Live TR | Verified paper TR | Cursor width |
| --- | --- | --- | --- |
| Domestic balance | TTTC8434R | VTTC8434R | 100 |
| Overseas balance | TTTS3012R | VTTS3012R | 200 |
| Domestic recent daily executions | TTTC0081R | VTTC0081R | 100 |
| Domestic older executions | CTSC9215R | VTSC9215R | 100 |
| Overseas executions | TTTS3035R | VTTS3035R | 200 |
| Domestic amendable/open orders | TTTC0084R | Not enabled | 100 |
| Overseas open orders | TTTS3018R | Not enabled | 200 |
| Domestic buying power | TTTC8908R | VTTC8908R | None |
| Domestic sellable | TTTC8408R | Not enabled | None |
| Overseas buying power | TTTS3007R | VTTS3007R | None |

For **live** overseas balance, open-order and execution inquiries, `NASD` means
all US markets, including NYSE/AMEX. This is explicitly documented separately in
`overseas_stock/inquire_balance/inquire_balance.py`,
`inquire_nccs/inquire_nccs.py`, and `inquire_ccnl/inquire_ccnl.py`.
For paper balance, NASD covers Nasdaq only. Paper execution history uses an empty
exchange parameter for all markets. Do not generalize one endpoint's semantics to
another. Buying power and orders use the instrument's exact NASD/NYSE/AMEX route.

Execution inquiries are cumulative order summaries. `ord_tmd` is an order time,
not a guaranteed per-fill timestamp. `tot_ccld_qty`/`ft_ccld_qty` must not be added
again at every poll. Their use for live quantity reconciliation does not make
them sufficient for exact completed-trade accounting; retain source statements.

Domestic cash limit enum is `00`; buy/sell use TTTC0012U/TTTC0011U. US cash limits
use `00`, TTTT1002U/TTTT1006U. US paper sell is deliberately disabled because the
sample's comment and generated ID disagree. Cancel/amend uses explicit native IDs,
remaining whole quantity, and domestic `KRX_FWDG_ORD_ORGNO` from the original ack.
A cancellation ack is not terminal proof; reconcile the original order and fills.

`search-info` CTPF1702R uses product types NASD=512, NYSE=513, AMEX=529. A read-only
live probe confirmed DRAM as `ROUNDHILL ETF TRUST MEMORY ETF`, AMEX/USD, listed,
not delisted, one-share buy/sell units. SPY and QPUX routes were also confirmed.
None of these observations proves cash-order acceptance or native protective support.

Domestic top-of-book returns `output1.aspr_acpt_hour`, `bidp1`, `askp1`; a current
intraday bar supplies the session date. Overseas top-of-book returns identity and
`dymd`/`dhms` in output1, `pbid1`/`pask1` in output2. Observed US quote receipt clocks
are KST; the execution calendar is New York. Treat clock validation as an explicit
in-session rollout check, never substitute request arrival time for source time.

KIS native protective SELL/trailing remains **unverified** for the target ETFs.
`CNDT_PRIC`, order names and HTS features alone are not evidence of Open API SL.
