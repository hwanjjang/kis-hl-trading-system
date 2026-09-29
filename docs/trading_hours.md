# Trading Hours Policy

Hyperliquid is a 24-hour venue and can quote and accept orders outside the underlying market's normal session. For Hyperliquid entries (native perps and trade.xyz RWA assets alike) the underlying-market session below is **advisory only**: it is recorded with each decision and should inform the review (thin off-session liquidity, unanchored pricing, weekend gaps), but it never blocks an order. KIS securities trading is different: KIS orders remain bound by the actual exchange session, auctions and tick rules. Entry timing for an HL RWA instrument follows its strategy signal (for example `hl:xyz:KORU` is judged by `index:KOSPI`), not the underlying listing's hours.

BTCUSDC futures use the Hyperliquid native BTC perp market and are treated as crypto perps, not trade.xyz RWA assets.

This document records the default session policy for the current tradable asset universe. It is a trading guard reference, not a complete holiday calendar.

## Default Policy

- Prefer regular cash-market hours for stocks, ETFs, and cash equity indexes.
- Prefer the underlying futures electronic session for commodity references.
- Treat FX as a 24/5 global market because there is no single centralized exchange.
- For KIS: do not use pre-market, after-hours or holiday sessions for normal live entries.
- For Hyperliquid: off-session, overnight and weekend entries are permitted; disclose the advisory session status and liquidity/pricing risk in the review.
- Allow position reduction outside these windows only when risk controls require it.

## Session Groups

| Session group | Default live-entry window | Current KST conversion during U.S. daylight saving time | Assets |
| --- | --- | --- | --- |
| U.S. cash equities | Monday-Friday 09:30-16:00 ET | 22:30-05:00 next calendar day | `SP500`, `XYZ100`, `KORU`, `URNM`, `TSLA`, `NVDA`, `GOOGL`, `INTC`, `MU`, `PLTR`, `ORCL`, `MSTR`, `MSFT`, `META`, `AMZN`, `AMD`, `AAPL`, `COIN`, `HOOD`, `NFLX`, `CRCL`, `SNDK`, `RIVN`, `USAR`, `TSM`, `BABA`, `CRWV`, `DKNG`, `HIMS`, `COST`, `LLY` |
| KRX cash equities | Monday-Friday 09:00-15:30 KST | 09:00-15:30 KST | `SKHYNIX`, `SAMSUNG`, `HYUNDAI` |
| TSE cash equities | Monday-Friday 09:00-11:30 and 12:30-15:30 JST | 09:00-11:30 and 12:30-15:30 KST | `JP225` |
| Commodity futures reference | Sunday 18:00 ET-Friday 17:00 ET, with a daily 17:00-18:00 ET maintenance break Monday-Thursday | Monday 07:00-Saturday 06:00 KST, with a daily 06:00-07:00 KST break during U.S. daylight saving time | `BRENTOIL`, `WTIOIL`, `NATGAS`, `COPPER`, `GOLD`, `SILVER`, `PLATINUM`, `PALLADIUM` |
| FX reference | Sunday 17:00 ET-Friday 17:00 ET | Monday 06:00-Saturday 06:00 KST during U.S. daylight saving time | `EUR`, `JPY` |

When the U.S. is not observing daylight saving time, U.S. ET based windows shift one hour later in KST.

## Asset Notes

- `SP500` and `XYZ100` are index references, not exchange-traded shares. The normal live-entry window should follow the U.S. cash equity session because their cash values are anchored to listed U.S. equities.
- `JP225` is a Nikkei 225 reference, not an exchange-traded share. The normal live-entry window should follow the Tokyo Stock Exchange cash session.
- `KORU` references a U.S.-listed leveraged South Korea ETF; its advisory session is the U.S. cash session, while entry timing follows the KOSPI signal and may occur at any HL trading time. It is not a KR200/KOSPI200 equivalent.
- `KR200` retains its KRX session mapping for historical/reference use, but is excluded from live eligibility; session availability does not override that exclusion.
- `BRENTOIL`, `WTIOIL`, `NATGAS`, and `COPPER` use rolling futures references in the trade.xyz specification.
- `GOLD`, `SILVER`, `PLATINUM`, and `PALLADIUM` are spot-style trade.xyz references, but the current secondary historical data mapping uses futures proxies. The default guard uses the overlapping CME/COMEX/NYMEX-style weekday futures window until an exact spot-metal session source is implemented.
- `EUR` and `JPY` are FX spot-style references. They do not have a single exchange session, so the guard should treat weekends as closed and weekdays as open unless a provider outage or special holiday rule is known.
- `BTCUSDC-PERP`, `BTC-PERP`, and `BTCPERP` resolve to the Hyperliquid `BTC` perp coin. The current session guard treats this market as 24/7.

## Implementation Requirements

Current implementation status:

- `kis_hl.trading_hours` implements timezone-aware session decisions for the groups above.
- Native BTC crypto spot and BTC perp sessions are treated as 24/7.
- `HyperliquidTradingClient.place_order()` records the session decision on live entries (`session`, `session_advisory_only`) but does not reject outside the mapped session. `--allow-outside-session` / `allow_outside_session` remain accepted for compatibility and have no blocking effect.
- The managed Hyperliquid gateway treats the session as open for execution and exposes the advisory decision as `session_advisory` in its preflight snapshot. The managed KIS gateway still enforces exchange sessions.
- Reduce-only exits, including stop-loss trigger orders, bypass the live-entry session guard.

Remaining requirements before autonomous trading:

- Add holiday and early-close calendars for NYSE/Nasdaq, KRX, JPX/TSE, CME/NYMEX/COMEX, and FX weekend boundaries.
- Keep time conversion timezone-aware. Do not hard-code KST offsets for U.S. markets because daylight saving time changes the conversion.
- Persist session decisions alongside strategy signals once autonomous signal execution exists.
- Add tests for official holiday and early-close fixtures after exchange calendars are selected.

## Sources

- trade.xyz Specification Index: https://docs.trade.xyz/consolidated-resources/specification-index
- trade.xyz Korea asset sessions: https://docs.trade.xyz/asset-directory/korea
- trade.xyz Holiday Closures: https://docs.trade.xyz/consolidated-resources/holiday-closures
- NYSE Trading Information: https://beta.nyse.com/trade/trading-information
- Nasdaq market hours: https://www.nasdaq.com/market-activity/stock-market-holiday-schedule
- KRX Guide to Trading in the Korean Stock Market: https://global.krx.co.kr/contents/GLB/01/0109/0109000000/guide_to_trading_in_the_korean_stock_market.pdf
- Japan Exchange Group trading hours: https://www.jpx.co.jp/english/equities/trading/domestic/01.html
- CME Group trading hours and holiday schedules: https://www.cmegroup.com/trading-hours.html
- CME FX futures overview: https://www.cmegroup.com/trading/why-futures/welcome-to-cme-fx-futures.html
- CME Gold futures fact card: https://www.cmegroup.com/market-regulation/files/gold-futures-and-options-fact-card.pdf
- CME Copper futures fact card: https://www.cmegroup.com/trading/metals/files/copper-futures-and-options.pdf

Native `ETH`, `ETH-PERP`, and `ETHUSDC-PERP` resolve to the Hyperliquid ETH
perpetual and use the same explicit 24/7 crypto-perpetual session as BTC. This
session mapping does not authorize any additional native or HIP-3 asset.
