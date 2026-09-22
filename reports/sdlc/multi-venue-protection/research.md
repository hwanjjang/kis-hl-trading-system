# Capability and instrument evidence

As of 2026-09-12. Public official-source research only. No private API calls,
account entitlements, live universe, or order submissions were tested in this task.
`Documented` means the cited API describes a facility; it is not operational proof.

## KIS interfaces

| Facility | Public evidence | Boundary |
| --- | --- | --- |
| Domestic cash order | [order_cash.py](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/order_cash/order_cash.py): order-cash; live buy TTTC0012U, sell TTTC0011U | Verify order code per instrument, side, venue, environment and session |
| Domestic stop-limit field | Same sample documents CNDT_PRIC | Does not prove falling-price sell protection for 069500/122630; exact semantics and eligibility remain a hard gate |
| Domestic amend/cancel | [order_rvsecncl.py](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/order_rvsecncl/order_rvsecncl.py), [inquire_psbl_rvsecncl.py](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_psbl_rvsecncl/inquire_psbl_rvsecncl.py) | Original order/organization IDs and currently amendable quantity required |
| Domestic fills | [inquire_daily_ccld.py](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/inquire_daily_ccld.py) | Paginate; filled/unfilled distinction |
| Overseas cash order | [order.py](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/order/order.py) | Different order types and paper restrictions; do not reuse domestic enum |
| Overseas amend/cancel | [order_rvsecncl.py](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/order_rvsecncl/order_rvsecncl.py) | Account, venue and remaining quantity verified before replacement |
| Overseas open orders/fills | [inquire_nccs.py](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_nccs/inquire_nccs.py), [inquire_ccnl.py](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_ccnl/inquire_ccnl.py) | Full pagination and exchange-filter semantics; open-order absence is not fill proof |
| KOSPI history | [inquire_daily_indexchartprice.py](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_indexchartprice/inquire_daily_indexchartprice.py): FHKUP03500100, U/0001 | KOSPI differs from current KR200 U/2001 mapping |
| S&P 500 index | [inquire_time_indexchartprice.py](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/inquire_time_indexchartprice/inquire_time_indexchartprice.py): FHKST03030200, N/SPX | Daily chart route also documented; cadence/history/entitlements untested |
| Nasdaq-100 index | Current repo maps N/NDX to same route | Verify exact symbol through official master and read-only data probe before use |
| ETF chart alternative | [dailyprice.py](https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/overseas_stock/dailyprice/dailyprice.py) | SPY/QQQ are separately labeled proxies, with their own exchange, adjusted-price and session settings |

The overseas order sample's text lists VTTT1001U for paper US sell, while its code
mechanically derives VTTT1006U. Some read samples also retain live-only IDs.
Resolve these inconsistencies against the current portal before implementation.
Do not derive every paper TR ID from the live name.

## Native protective semantics

- [Hyperliquid exchange API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint)
  documents trigger SL/TP, reduceOnly and grouping. The
  [official SDK example](https://github.com/hyperliquid-dex/hyperliquid-python-sdk/blob/master/examples/basic_tpsl.py)
  submits grouped parent and children. This repo does not yet expose grouped entry.
- [Hyperliquid TP/SL semantics](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/take-profit-and-stop-loss-orders-tp-sl):
  mark-price triggering; grouped children have activation/cancellation conditions
  around full and partial parent fills. Submission acceptance alone is not coverage.
  Fixed order sizes must be reconciled as exposure changes.
- No trailing type/field was identified in the reviewed Hyperliquid exchange/order
  documents. Native trailing remains unverified; reuse local trailing as proposed.
- KIS overseas native SL and domestic/overseas native trailing are unverified in
  reviewed public stock APIs. An HTS feature or a backtest option is not API evidence.
- KIS domestic CNDT_PRIC establishes a field only. To classify protective SL require
  falling-price SELL trigger, post-trigger execution behavior, expiry, eligible
  instrument/exchange/session and API manageability. Exact verification is separate.

## Instrument identities

| Instrument | Issuer/exchange evidence | Mapping consequence |
| --- | --- | --- |
| 069500 | [Samsung KODEX 200](https://www.samsungfund.com/etf/product/view.do?id=2ETF01&isBanner=Y) | KOSPI200 exposure; not the KOSPI broad index |
| 122630 | [Samsung KODEX Leverage](https://m.samsungfund.com/etf/product/view.do?id=2ETF25) | Daily 2x KOSPI200 objective; no fixed conversion from index price |
| SPY | [State Street](https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy) | S&P500 ETF |
| UPRO | [ProShares](https://www.proshares.com/our-etfs/leveraged-and-inverse/upro) | Daily 3x S&P500 objective |
| QQQ | [Invesco](https://www.invesco.com/qqq-etf/en/about.html) | Nasdaq-100 ETF, not Nasdaq Composite |
| TQQQ | [ProShares](https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq) | Daily 3x Nasdaq-100 objective |
| GLD | [SPDR Gold Shares](https://www.spdrgoldshares.com/usa/) | User confirmed KIS gold ETF; distinct units/price from HL GOLD |
| QPUX | [Defiance](https://www.defianceetfs.com/qpux/) | Defiance 2X Daily Long Pure Quantum ETF; NASDAQ; inception 2025-08-06 |
| DRAM | [Roundhill](https://www.roundhillinvestments.com/etf/dram/), [Cboe SEC listing certificate](https://www.sec.gov/Archives/edgar/data/1976517/000141783526000077/8A_Cert_DRAM.pdf) | Roundhill Memory ETF; Cboe BZX; launch 2026-04-02; KIS quote/order route requires verification |

The stock-specific 30-week live eligibility rule must not silently become a new
ETF exclusion or exemption policy. DRAM has less than 30 weeks of ETF history at
this date; a strategy requiring a 30-week indicator fails its data sufficiency
check without fabricating pre-launch bars. This is independent of stock age policy.

[trade.xyz documentation](https://docs.trade.xyz/) establishes HIP-3 asset classes,
not the exact current listing or ETF identity for every candidate. Existing
SP500/XYZ100/GOLD seeds are discovery candidates, not fresh verification. BTC/ETH
metadata and current resolver/allowlist support also require explicit tests before
expanding execution. No HL DRAM-to-ETF equivalence is assumed.

## Exact KIS protective-order verification follow-up

User correction: domestic/overseas order types and protective semantics must be
confirmed separately; names are not proof. The bounded official-source follow-up
found [KIS stock-trading explanation](https://file.koreainvestment.com/updata/namo/21093445%EC%A3%BC%EC%8B%9D%EA%B1%B0%EB%9E%98%EC%84%A4%EB%AA%85%EC%84%9C_%EC%A0%84%EB%AC%B8.pdf)
describing activation into a specified limit order. Extracted tables mention both
KRX and NXT, so NXT-only support is not asserted. PDF table screenshots could not
be verified in that research pass; table-level eligibility is not relied upon.
[NXT overview](https://www.nextrade.co.kr/marketOverview/content.do) confirms the
order family, not KIS API acceptance for a requested ETF.

| Protective dimension | Requested domestic ETFs | Requested US ETFs |
| --- | --- | --- |
| Exact KIS API protective enum | Unverified | Unverified |
| SELL downside comparator and gap handling | Unverified | Unverified |
| Trigger reference price and venue | Unverified | Unverified |
| Post-trigger behavior | General domestic description says limit; ETF/API mapping unverified | Unverified |
| Pending/triggered expiry and session carryover | Unverified | Unverified |
| Exact instrument/account/environment acceptance | Unverified | Unverified |
| API-visible cancel/amend/status for protection | Unverified | Unverified |
| Native trailing persistence and ratchet behavior | Unverified | Unverified |

All remain disabled native-protection candidates. A future verification record
must name the exact product, side, API schema/version, trigger comparator/feed,
post-trigger type, expiry/session and environment, with source and executable
validation evidence. Do not perform an actual order probe under planning authority.

The [KIS portal](https://apiportal.koreainvestment.com/intro) and
[KIS homepage](https://securities.koreainvestment.com/main/Main.jsp) also carry
September 2026 market-session change notices. Revalidate effective dates against
the current notice before implementation rather than freezing an older timetable.

## Harness / journal / notification amendment

The user requires actual-fill journals across agent, HTS and web execution, updated
on demand or periodically. The selected interval is three hours, configurable.
This is distinct from real-time protection and strategy signal cadence.

[HL info API](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint)
documents userFillsByTime, an inclusive time window, optional aggregation and a
2,000-result response cap with only the latest 10,000 fills available. Its fill
examples contain native execution/order identity, fee token and optional builder
fee already included in the total fee. Source retrieval is account-oriented, not
dependent on this repo's local intents. Exact HTS/web inclusion and KIS cumulative
row semantics still need account-specific read-only validation. Retention gaps
require explicit pending state and source-backed import, not invented fills.

[Notification recommendation](../../../docs/product/trading-notifications.md)
compares official Telegram, ntfy and Slack interfaces, checked 2026-09-12. Telegram
is a recommendation for a personal operator, not a measured reliability ranking.
No notification was sent and no schedule was installed.
