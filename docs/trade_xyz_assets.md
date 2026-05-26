# trade.xyz Asset Mapping

This project keeps a local SQLite seed table for trade.xyz RWA markets. The table is intentionally curated rather than scraped at runtime because live trading should fail closed when mappings or eligibility are unclear.

## Eligibility Rules

- Include current or explicitly configured trade.xyz index, ETF, and single-name equity assets.
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

Important columns:

- `trade_symbol`: trade.xyz market symbol.
- `hyperliquid_coin`: expected Hyperliquid HIP-3 coin, using the `xyz:` prefix.
- `asset_class`: `equity_index`, `etf`, or `stock`.
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
- `SP500` uses the KIS overseas index intraday chart endpoint with index code `SPX`.
- `JP225` uses the KIS overseas index intraday chart endpoint with index code `JP#NI225`.
- `XYZ100` remains `unsupported` because it is a trade.xyz proprietary index without a KIS source route.
- `EWY` and `EWJ` retain quote mappings for auditability but are `excluded` because this project trades `KR200` and `JP225` instead.

Operational commands:

```bash
python -m kis_hl.cli xyz-assets kis-list --status active
python -m kis_hl.cli xyz-assets kis-fetch --symbol SAMSUNG --store
python -m kis_hl.cli xyz-assets kis-collect --symbols SAMSUNG KR200 SP500 --delay-ms 300
```

`kis-fetch` and `kis-collect` store raw KIS payloads in `market_ticks` with `market` set to values such as `trade_xyz_domestic`, `trade_xyz_overseas`, `trade_xyz_domestic_index`, or `trade_xyz_overseas_index_time`.

## Verification Notes

The table is based on the trade.xyz specification index and asset directory, plus project-specific duplicate exposure rules. Before enabling a new live asset, verify that Hyperliquid `allMids` or metadata exposes the expected `xyz:<symbol>` market.

Live trade.xyz order submission requires both:

- `trade_xyz_assets.tradable = 1`
- A recent successful `trade_xyz_asset_checks` row for the expected `hyperliquid_coin`; the CLI default freshness window is 24 hours.

Some project-friendly canonical symbols differ from trade.xyz/Hyperliquid market keys. For example, Samsung Electronics is stored as `SAMSUNG` but maps to `xyz:SMSN`, and SK hynix is stored as `SKHYNIX` but maps to `xyz:SKHX`.
