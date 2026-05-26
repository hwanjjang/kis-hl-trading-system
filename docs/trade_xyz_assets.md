# trade.xyz Asset Mapping

This project keeps a local SQLite seed table for trade.xyz RWA markets. The table is intentionally curated rather than scraped at runtime because live trading should fail closed when mappings or eligibility are unclear.

## Eligibility Rules

- Include current or explicitly configured trade.xyz index, ETF, and single-name equity assets.
- Exclude assets that have not completed a public listing or IPO.
- Prefer direct index exposure over ETF proxy exposure when both serve the same trading objective:
  - `KR200` is the preferred South Korea exposure; `EWY` is excluded.
  - `JP225` is the preferred Japan exposure; `EWJ` is excluded.
- Treat excluded rows as documentation and guardrails, not trade candidates.

## SQLite Table

`trade_xyz_assets` is created by `init_db()` and populated by `seed_trade_xyz_assets()`.

Important columns:

- `trade_symbol`: trade.xyz market symbol.
- `hyperliquid_coin`: expected Hyperliquid HIP-3 coin, using the `xyz:` prefix.
- `asset_class`: `equity_index`, `etf`, or `stock`.
- `underlying_symbol`: source market symbol, index name, ETF ticker, or KRX ticker.
- `listing_status`: `listed`, `not_applicable`, or another explicit status.
- `tradable`: `1` only when this project may trade the asset.
- `exclusion_reason`: populated for excluded assets.
- `duplicate_group` and `preferred_symbol`: document equivalent exposure decisions.

## Verification Notes

The table is based on the trade.xyz specification index and asset directory, plus project-specific duplicate exposure rules. Before enabling a new live asset, verify that Hyperliquid `allMids` or metadata exposes the expected `xyz:<symbol>` market.

