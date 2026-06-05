# Trading Hours Policy

Hyperliquid can quote and accept orders outside the underlying market's normal session. This project should only open or increase live trade.xyz positions during the relevant underlying market session unless an explicit strategy override is added for a special case.

BTCUSDC futures use the Hyperliquid native BTC perp market and are treated as crypto perps, not trade.xyz RWA assets.

This document records the default session policy for the current tradable asset universe. It is a trading guard reference, not a complete holiday calendar.

## Default Policy

- Prefer regular cash-market hours for stocks, ETFs, and cash equity indexes.
- Prefer the underlying futures electronic session for commodity references.
- Treat FX as a 24/5 global market because there is no single centralized exchange.
- Do not use pre-market, after-hours, overnight internal pricing, or weekend pricing for normal live entries.
- Do not open or increase positions on official exchange holidays or early-close windows after the shortened close.
- Allow position reduction outside these windows only when risk controls require it.

## Session Groups

| Session group | Default live-entry window | Current KST conversion during U.S. daylight saving time | Assets |
| --- | --- | --- | --- |
| U.S. cash equities | Monday-Friday 09:30-16:00 ET | 22:30-05:00 next calendar day | `SP500`, `XYZ100`, `URNM`, `TSLA`, `NVDA`, `GOOGL`, `INTC`, `MU`, `PLTR`, `ORCL`, `MSTR`, `MSFT`, `META`, `AMZN`, `AMD`, `AAPL`, `COIN`, `HOOD`, `NFLX`, `CRCL`, `SNDK`, `RIVN`, `USAR`, `TSM`, `BABA`, `CRWV`, `DKNG`, `HIMS`, `COST`, `LLY` |
| KRX cash equities | Monday-Friday 09:00-15:30 KST | 09:00-15:30 KST | `KR200`, `SKHYNIX`, `SAMSUNG`, `HYUNDAI` |
| TSE cash equities | Monday-Friday 09:00-11:30 and 12:30-15:30 JST | 09:00-11:30 and 12:30-15:30 KST | `JP225` |
| Commodity futures reference | Sunday 18:00 ET-Friday 17:00 ET, with a daily 17:00-18:00 ET maintenance break Monday-Thursday | Monday 07:00-Saturday 06:00 KST, with a daily 06:00-07:00 KST break during U.S. daylight saving time | `BRENTOIL`, `WTIOIL`, `NATGAS`, `COPPER`, `GOLD`, `SILVER`, `PLATINUM`, `PALLADIUM` |
| FX reference | Sunday 17:00 ET-Friday 17:00 ET | Monday 06:00-Saturday 06:00 KST during U.S. daylight saving time | `EUR`, `JPY` |

When the U.S. is not observing daylight saving time, U.S. ET based windows shift one hour later in KST.

## Asset Notes

- `SP500` and `XYZ100` are index references, not exchange-traded shares. The normal live-entry window should follow the U.S. cash equity session because their cash values are anchored to listed U.S. equities.
- `JP225` is a Nikkei 225 reference, not an exchange-traded share. The normal live-entry window should follow the Tokyo Stock Exchange cash session.
- `KR200` should follow the KRX cash equity session.
- `BRENTOIL`, `WTIOIL`, `NATGAS`, and `COPPER` use rolling futures references in the trade.xyz specification.
- `GOLD`, `SILVER`, `PLATINUM`, and `PALLADIUM` are spot-style trade.xyz references, but the current secondary historical data mapping uses futures proxies. The default guard uses the overlapping CME/COMEX/NYMEX-style weekday futures window until an exact spot-metal session source is implemented.
- `EUR` and `JPY` are FX spot-style references. They do not have a single exchange session, so the guard should treat weekends as closed and weekdays as open unless a provider outage or special holiday rule is known.
- `BTCUSDC-PERP`, `BTC-PERP`, and `BTCPERP` resolve to the Hyperliquid `BTC` perp coin. The current session guard treats this market as 24/7.

## Implementation Requirements

Current implementation status:

- `kis_hl.trading_hours` implements timezone-aware session decisions for the groups above.
- Native BTC crypto spot and BTC perp sessions are treated as 24/7.
- `HyperliquidTradingClient.place_order()` rejects live non-reduce-only trade.xyz orders outside the mapped session unless `allow_outside_session=True`.
- The CLI exposes the explicit override as `--allow-outside-session`.
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
