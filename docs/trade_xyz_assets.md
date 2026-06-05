# trade.xyz Asset Mapping

This project keeps a local SQLite seed table for trade.xyz RWA markets. The table is intentionally curated rather than scraped at runtime because live trading should fail closed when mappings or eligibility are unclear.

## Eligibility Rules

- Include current or explicitly configured trade.xyz index, commodity, FX, ETF, and single-name equity assets.
- Exclude assets that have not completed a public listing or IPO.
- Exclude stock assets that have traded on a public securities exchange for less than 30 weeks.
- Prefer direct index exposure over ETF proxy exposure when both serve the same trading objective:
  - `KR200` is the preferred South Korea exposure; `EWY` is excluded.
  - `JP225` is the preferred Japan exposure; `EWJ` is excluded.
- Treat excluded rows as documentation and guardrails, not trade candidates.

## SQLite Table

`trade_xyz_assets` is created by `init_db()` and populated by `seed_trade_xyz_assets()`.
`trade_xyz_asset_checks` stores point-in-time Hyperliquid metadata verification results from `xyz-assets verify`.
`trade_xyz_kis_mappings` stores the KIS market-data route for each trade.xyz asset when this project has an implemented KIS quote path.
`trade_xyz_reference_mappings` stores secondary market-data mappings for assets where KIS is unavailable or a cross-check is useful.
`market_daily_bars` stores idempotent daily OHLCV bars by `(source, market, symbol, bar_date)`.
`trade_xyz_universe_snapshots` stores point-in-time Hyperliquid `xyz` universe snapshots and records newly added or missing symbols.
`trade_xyz_universe_assets` stores the per-market metadata from each universe snapshot, including Hyperliquid `dayBaseVlm`, `dayNtlVlm`, and `openInterest` as queryable columns when present.
`market_funding_rates` stores Hyperliquid hourly funding-rate history by `xyz` symbol and funding timestamp.
`market_spread_snapshots` stores Hyperliquid top-of-book spread snapshots for liquidity and execution-cost review.

Important columns:

- `trade_symbol`: trade.xyz market symbol.
- `hyperliquid_coin`: expected Hyperliquid HIP-3 coin, using the `xyz:` prefix.
- `asset_class`: `commodity`, `equity_index`, `etf`, `fx`, or `stock`.
- `underlying_symbol`: source market symbol, index name, ETF ticker, or KRX ticker.
- `listing_status`: `listed`, `not_applicable`, or another explicit status.
- `listing_date`: first public trading date for stock assets.
- `min_listing_age_weeks`: minimum listing age required before stock assets become tradable.
- `tradable`: `1` only when this project may trade the asset. This is computed at seed time from the configured eligibility flags and listing-age rule.
- `exclusion_reason`: populated for excluded assets.
- `duplicate_group` and `preferred_symbol`: document equivalent exposure decisions.

## KIS Market-Data Mapping

`trade_xyz_kis_mappings` is populated by `seed_trade_xyz_kis_mappings()` or:

```bash
python -m kis_hl.cli xyz-assets seed-kis
```

Important columns:

- `trade_symbol`: canonical project symbol, such as `SAMSUNG`, `SKHYNIX`, or `KR200`.
- `hyperliquid_coin`: expected Hyperliquid HIP-3 coin, such as `xyz:SMSN`.
- `kis_market`: `domestic`, `overseas`, `domestic_index`, `overseas_index_time`, or `unsupported`.
- `kis_symbol`: the KIS quote symbol. Korean stocks strip the `.KS` suffix, so Samsung maps to `005930`.
- `kis_exchange_code`: KIS overseas quote exchange code. This uses price quote codes such as `NAS`, `NYS`, and `AMS`, not overseas order codes such as `NASD`, `NYSE`, or `AMEX`.
- `kis_market_code`: KIS domestic market division code, currently `J` for listed Korean stocks.
- `status`: `active`, `excluded`, or `unsupported`.
- `reason`: why an excluded or unsupported mapping cannot be used by `kis-fetch`.

Current route policy:

- KRX stocks use the KIS domestic stock `inquire-price` endpoint.
- U.S. stocks use the KIS overseas `price` endpoint with `NAS` or `NYS`.
- NYSE Arca ETFs use `AMS` for the KIS overseas quote route and must be live-checked before a new ETF is traded.
- `KR200` uses the KIS domestic index current-price endpoint with index code `2001`.
- `XYZ100` maps to Nasdaq 100 and uses the KIS overseas index intraday chart endpoint with index code `NDX`.
- `SP500` uses the KIS overseas index intraday chart endpoint with index code `SPX`.
- `JP225` uses the KIS overseas index intraday chart endpoint with index code `JP#NI225`.
- `EWY` and `EWJ` retain quote mappings for auditability but are `excluded` because this project trades `KR200` and `JP225` instead.
- `BRENTOIL`, `WTIOIL`, `NATGAS`, and `COPPER` preserve their futures root references (`BZ`, `CL`, `NG`, and `HG`) but are `unsupported` until KIS overseas futures `SRS_CD` front-contract resolution is implemented.
- `GOLD`, `SILVER`, `PLATINUM`, and `PALLADIUM` preserve their spot metal references (`XAUUSD`, `XAGUSD`, `XPTUSD`, and `XPDUSD`) but are `unsupported` because a KIS futures quote would be a proxy, not the exact trade.xyz spot reference.
- `JPY` and `EUR` preserve their FX references (`USDJPY` and `EURUSD`) but are `unsupported` until a KIS FX quote route is implemented.

Operational commands:

```bash
python -m kis_hl.cli xyz-assets kis-list --status active
python -m kis_hl.cli xyz-assets kis-fetch --symbol SAMSUNG --store
python -m kis_hl.cli xyz-assets kis-collect --symbols SAMSUNG KR200 SP500 --delay-ms 300
```

`kis-fetch` and `kis-collect` store raw KIS payloads in `market_ticks` with `market` set to values such as `trade_xyz_domestic`, `trade_xyz_overseas`, `trade_xyz_domestic_index`, or `trade_xyz_overseas_index_time`.

## Secondary Reference-Data Mapping

`trade_xyz_reference_mappings` is populated by:

```bash
python -m kis_hl.cli xyz-assets seed-ref
```

Current provider policy:

- `yahoo_finance` is implemented through Yahoo Finance chart endpoints with standard library HTTP calls; the project does not require the external `yfinance` package.
- Index fallbacks use `^KS200`, `^GSPC`, `^NDX`, and `^N225`.
- Commodity fallbacks use continuous futures tickers: `BZ=F`, `CL=F`, `NG=F`, `HG=F`, `GC=F`, `SI=F`, `PL=F`, and `PA=F`.
- FX fallbacks use `EURUSD=X` and `JPY=X`.
- Yahoo data is a secondary reference source only. It may be rate-limited, delayed, or use provider-specific futures roll rules, so live trading guards must not treat it as exchange-licensed primary data.

Operational commands:

```bash
python -m kis_hl.cli xyz-assets ref-list --status active
python -m kis_hl.cli xyz-assets ref-fetch --symbol GOLD --store
python -m kis_hl.cli xyz-assets ref-collect --asset-class commodity --delay-ms 300
```

`ref-fetch` and `ref-collect` store normalized Yahoo chart payloads in `market_ticks` with `source = yahoo_finance` and `market = trade_xyz_reference_yahoo_finance`.

## Daily Bar Collection

Daily bar collection uses Yahoo Finance chart data to provide one broad historical source across the full tradable trade.xyz universe:

```bash
python -m kis_hl.cli xyz-assets daily-collect --days 365 --delay-ms 300
```

Route policy:

- Commodity, FX, and index assets use `trade_xyz_reference_mappings`.
- Stock and ETF assets use the `underlying_symbol` from `trade_xyz_assets`; KRX assets keep their `.KS` Yahoo suffix.
- Rows are upserted into `market_daily_bars`, so rerunning the command refreshes existing dates rather than creating duplicates.
- `--to YYYY-MM-DD` is an exclusive end date; with `--days 365`, `--to 2026-05-27` collects from `2025-05-27` through the available trading days before `2026-05-27`.

Yahoo daily bars are a broad historical reference. KIS remains the preferred source for active KIS routes when exact Korean broker data is required.

## Hyperliquid xyz Market Data

The live Hyperliquid `xyz` universe can change independently from the curated eligibility seed. Track that universe daily before reviewing new trade candidates:

```bash
python -m kis_hl.cli xyz-assets universe-collect
```

The command stores the full `metaAndAssetCtxs` response in SQLite and reports:

- `new_symbols`: symbols present in the current Hyperliquid `xyz` universe but absent from the previous snapshot, or absent from the curated seed on the first run.
- `missing_symbols`: symbols previously seen but absent from the current snapshot.
- `unmapped_symbols`: current live `xyz` symbols that are not in the curated `trade_xyz_assets` seed.
- `assets_with_day_base_volume`, `assets_with_day_notional_volume`, and `assets_with_open_interest`: counts of assets whose context included the corresponding Hyperliquid liquidity fields.

New symbols remain observation-only until the curated asset table, eligibility rules, market-data mapping, trading-hours policy, and tests are updated.

Funding history collection stores hourly Hyperliquid funding rows:

```bash
python -m kis_hl.cli xyz-assets funding-collect --lookback-hours 24 --delay-ms 300
python -m kis_hl.cli xyz-assets funding-collect --symbols SP500 XYZ100 GOLD DRAM --lookback-hours 168
```

Spread collection stores the current best bid, best ask, mid price, absolute spread, spread bps, and top-level sizes:

```bash
python -m kis_hl.cli xyz-assets spread-collect --delay-ms 300
python -m kis_hl.cli xyz-assets spread-collect --symbols SP500 XYZ100 GOLD DRAM
```

Funding and spread data should be reviewed before opening or adding to a position. They are suitability inputs, not standalone trade signals.

## Verification Notes

The table is based on the trade.xyz specification index and asset directory, plus project-specific duplicate exposure rules. Before enabling a new live asset, verify that Hyperliquid `allMids` or metadata exposes the expected `xyz:<symbol>` market.

Trading-hour policy is documented in `docs/trading_hours.md`. Normal live entries should use the underlying market's regular session, even when Hyperliquid quotes the market outside that session.

Live trade.xyz order submission requires both:

- `trade_xyz_assets.tradable = 1`
- A recent successful `trade_xyz_asset_checks` row for the expected `hyperliquid_coin`; the CLI default freshness window is 24 hours.

Some project-friendly canonical symbols differ from trade.xyz/Hyperliquid market keys. For example, Samsung Electronics is stored as `SAMSUNG` but maps to `xyz:SMSN`, SK hynix is stored as `SKHYNIX` but maps to `xyz:SKHX`, and WTI crude oil is stored as `WTIOIL` but maps to `xyz:CL`.
