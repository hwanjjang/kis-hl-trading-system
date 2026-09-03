# Information Architecture

## Interaction model

The product is a command hierarchy, not a page hierarchy. Global context is supplied before the command, command-specific inputs follow it, successful output is JSON on stdout, operational logs use configured structured logging, and command failures return JSON on stderr with a non-zero exit.

```text
kis-hl
├── --db <sqlite-path>
├── kis-price
├── kis-daily
├── hl-mids
├── hl-candles
├── hl-account
├── resolve-symbol
├── btc-3h-breakout
├── btc-3h-monitor
├── trade
├── journal
│   ├── add
│   └── stats
└── xyz-assets
    ├── seed
    ├── list
    ├── verify
    ├── universe-collect
    ├── funding-collect
    ├── spread-collect
    ├── seed-kis
    ├── kis-list
    ├── kis-fetch
    ├── kis-collect
    ├── seed-ref
    ├── ref-list
    ├── ref-fetch
    ├── ref-collect
    └── daily-collect
```

## Capability domains

| Domain | Purpose | Screen prefix | Primary data |
| --- | --- | --- | --- |
| Core | Discover command groups and select local database | CORE | CLI help, database path |
| Market | Direct KIS and Hyperliquid observations | MARKET | Raw quote, mids, candles |
| Account | Wallet-visible asset state | ACCOUNT | Perp, spot, optional dex states |
| Strategy | Deterministic BTC signal and monitor result | STRATEGY | Candles, ATR, plan/execution payloads |
| Order | Dry-run or signed Hyperliquid order | ORDER | Resolved asset, request, response, stored IDs |
| Journal | Completed trade capture and statistics | JOURNAL | Flat-to-flat records and nine metrics |
| Asset | Curated eligibility and observed trade.xyz market evidence | ASSET | Asset map, checks, universe, funding, spread |
| KIS mapping | Curated trade.xyz-to-KIS route and collection | KISMAP | Route metadata and KIS responses |
| Reference mapping | Secondary provider route and collection | REFMAP | Provider mapping and quote responses |
| History | Daily data needed by ATR/trend review | HISTORY | Normalized daily OHLCV bars |

## Information hierarchy

1. **Environment:** sandbox/live endpoints, key profile, base URLs, logging level.
2. **Local state target:** the exact SQLite path passed via `--db`.
3. **Instrument identity:** input symbol → resolved L1 coin → kind/dex → live order coin where applicable.
4. **Eligibility:** curated tradable/excluded state and reason.
5. **Verification:** latest metadata availability and observation timestamp.
6. **Market evidence:** source, route, timestamp, quote/candle/funding/spread/daily bars.
7. **Decision evidence:** signal values, ATR, session decision, dry-run/live intent.
8. **Execution evidence:** request, exchange response, status, timestamp, stored identifiers.
9. **Review evidence:** completed-trade record and statistics population/filters.

## Source-to-surface mapping

| Source | Read surfaces | Local write surfaces |
| --- | --- | --- |
| KIS REST | MARKET-001, MARKET-002, KISMAP-003, KISMAP-004 | Optional/direct or default/batch market tick payloads |
| Hyperliquid `/info` | MARKET-003, MARKET-004, ACCOUNT-001, STRATEGY-001, ASSET-004 through ASSET-007 | Verification, universe, funding, spread where enabled |
| Hyperliquid WebSocket | STRATEGY-002 | Order/protective evidence produced by executions |
| Hyperliquid signed exchange | ORDER-001, STRATEGY-002 in live mode | Order and protective-order records |
| Yahoo Finance | REFMAP-003, REFMAP-004, HISTORY-001 | Reference ticks and daily bars |
| SQLite only | ASSET-002, ASSET-003, KISMAP-001, KISMAP-002, REFMAP-001, REFMAP-002, JOURNAL-001, JOURNAL-002 | Mapping seeds, journal entries, snapshots |

## Local persistence model

| Information | SQLite table(s) | Producer surfaces |
| --- | --- | --- |
| Raw/current market payloads | `market_ticks` | MARKET-001, MARKET-002, KISMAP-003/004, REFMAP-003/004 |
| Daily OHLCV | `market_daily_bars` | HISTORY-001 |
| Funding | `market_funding_rates` | ASSET-006 |
| Spread | `market_spread_snapshots` | ASSET-007 |
| Order audit | `order_submissions` | ORDER-001, STRATEGY-002 |
| Protective stop audit | `protective_orders` | ORDER-001, STRATEGY-002 |
| Completed trade review | `trade_journal_entries` | JOURNAL-001 |
| Curated trade.xyz eligibility | `trade_xyz_assets` | ASSET-002 |
| Metadata verification | `trade_xyz_asset_checks` | ASSET-004 |
| KIS route map | `trade_xyz_kis_mappings` | KISMAP-001 |
| Secondary route map | `trade_xyz_reference_mappings` | REFMAP-001 |
| Observed trade.xyz universe | `trade_xyz_universe_snapshots`, `trade_xyz_universe_assets` | ASSET-005 |

## Cross-document traceability

- User responsibility: `personas.md`.
- User motivation: `jobs-to-be-done.md`.
- Entry and branch order: `user-flows.md`.
- Canonical screen IDs and commands: `screen-inventory.md`.
- Per-surface states and completion: `screen-specs.md`.
- Testable outcomes: `acceptance-criteria.md`.

## Assumptions

- **A-002:** Each leaf command and each command-group index is treated as a screen-equivalent surface.
- **A-012:** Direct database inspection is an administrative fallback, not a first-class product surface.
- **A-013:** Structured logs are diagnostic context, not a separate user navigation area.

## Unresolved risks

- `journal` and `xyz-assets` without a leaf command currently fall back to root help instead of dedicated contextual help.
- There is no first-class history/list/detail navigation for stored orders, protective orders, raw market ticks, or universe snapshots.
- A future graphical UI cannot reuse this hierarchy unchanged without deciding roles, navigation depth, confirmation, and mobile behavior.
