# Screen Inventory

## Inventory rules

- The inventory describes current CLI surfaces, not proposed graphical pages.
- Every screen ID appears exactly once in `screen-specs.md`.
- Command-group indices are included because users enter them to discover child operations, even though current no-subcommand behavior falls back to root help.
- “Write” distinguishes local persistence from an external financial write.

## Core and direct market surfaces

| ID | Screen name | Surface type | CLI entry | Primary job | Write behavior |
| --- | --- | --- | --- | --- | --- |
| CORE-001 | Command index | Command index/help | `kis-hl` / `python -m kis_hl.cli` | JTBD-01 | None |
| MARKET-001 | KIS quote result | Single operation | `kis-price` | JTBD-02 | Optional local `market_ticks` |
| MARKET-002 | KIS overseas daily chart result | Single operation | `kis-daily` | JTBD-02 | Optional local `market_ticks` |
| MARKET-003 | Hyperliquid mids result | Single operation | `hl-mids` | JTBD-02 | None |
| MARKET-004 | Hyperliquid candle result | Single operation | `hl-candles` | JTBD-02 | None |
| ACCOUNT-001 | Hyperliquid account state | Single operation | `hl-account` | JTBD-10 | None |
| ASSET-001 | Hyperliquid symbol resolution | Single operation | `resolve-symbol` | JTBD-04, JTBD-13 | None |

## Strategy, order, and journal surfaces

| ID | Screen name | Surface type | CLI entry | Primary job | Write behavior |
| --- | --- | --- | --- | --- | --- |
| STRATEGY-001 | BTC 3-hour breakout evaluation | Single operation | `btc-3h-breakout` | JTBD-11 | None |
| STRATEGY-002 | BTC breakout monitor | Long-running operation | `btc-3h-monitor` | JTBD-12, JTBD-15 | Local order/protective rows by default; external orders only with `--live` |
| ORDER-001 | Hyperliquid order preparation/submission | High-risk operation | `trade` | JTBD-13 through JTBD-15 | Local order row by default; external order only with `--live` |
| CORE-002 | Journal command index | Command-group index/help | `journal` | JTBD-16, JTBD-17 | None |
| JOURNAL-001 | Completed trade entry result | Local write operation | `journal add` | JTBD-16 | Local `trade_journal_entries` |
| JOURNAL-002 | Trade statistics report | Local read/report | `journal stats` | JTBD-17 | None |

## trade.xyz asset and market-evidence surfaces

| ID | Screen name | Surface type | CLI entry | Primary job | Write behavior |
| --- | --- | --- | --- | --- | --- |
| CORE-003 | trade.xyz asset command index | Command-group index/help | `xyz-assets` | JTBD-03 through JTBD-09 | None |
| ASSET-002 | Seed curated asset map | Local write operation | `xyz-assets seed` | JTBD-04 | Local `trade_xyz_assets` |
| ASSET-003 | Curated asset list | Local list/report | `xyz-assets list` | JTBD-04 | None |
| ASSET-004 | Hyperliquid metadata verification | Batch verification | `xyz-assets verify` | JTBD-05 | Local `trade_xyz_asset_checks` |
| ASSET-005 | Live trade.xyz universe snapshot | Batch collection | `xyz-assets universe-collect` | JTBD-03 | Local universe snapshot by default |
| ASSET-006 | Funding history collection | Batch collection | `xyz-assets funding-collect` | JTBD-06, JTBD-18 | Local funding rows by default |
| ASSET-007 | Spread snapshot collection | Batch collection | `xyz-assets spread-collect` | JTBD-06, JTBD-18 | Local spread rows by default |

## KIS mapping surfaces

| ID | Screen name | Surface type | CLI entry | Primary job | Write behavior |
| --- | --- | --- | --- | --- | --- |
| KISMAP-001 | Seed KIS mappings | Local write operation | `xyz-assets seed-kis` | JTBD-07 | Local `trade_xyz_kis_mappings` |
| KISMAP-002 | KIS mapping list | Local list/report | `xyz-assets kis-list` | JTBD-07 | None |
| KISMAP-003 | Mapped KIS quote result | Single operation | `xyz-assets kis-fetch` | JTBD-07 | Optional local `market_ticks` |
| KISMAP-004 | Mapped KIS quote batch | Batch collection | `xyz-assets kis-collect` | JTBD-07, JTBD-18 | Local market ticks by default |

## Secondary reference and history surfaces

| ID | Screen name | Surface type | CLI entry | Primary job | Write behavior |
| --- | --- | --- | --- | --- | --- |
| REFMAP-001 | Seed secondary mappings | Local write operation | `xyz-assets seed-ref` | JTBD-08 | Local `trade_xyz_reference_mappings` |
| REFMAP-002 | Secondary mapping list | Local list/report | `xyz-assets ref-list` | JTBD-08 | None |
| REFMAP-003 | Mapped secondary quote result | Single operation | `xyz-assets ref-fetch` | JTBD-08 | Optional local `market_ticks` |
| REFMAP-004 | Mapped secondary quote batch | Batch collection | `xyz-assets ref-collect` | JTBD-08, JTBD-18 | Local market ticks by default |
| HISTORY-001 | Daily OHLCV collection | Batch collection | `xyz-assets daily-collect` | JTBD-09, JTBD-18 | Local `market_daily_bars` by default |

## Coverage summary

| Category | Count |
| --- | ---: |
| Command-group/index surfaces | 3 |
| Direct market/account/symbol surfaces | 6 |
| Strategy/order/journal leaf surfaces | 5 |
| Asset and live-market evidence surfaces | 6 |
| KIS mapping surfaces | 4 |
| Secondary mapping/history surfaces | 5 |
| **Total** | **29** |

## Deliberately excluded surfaces

- `.env` editing, direct SQLite queries, log viewers, token-cache files, and test commands are supporting tools rather than product screens.
- Planned strategy-daemon, trailing-stop, fill-reconciliation, notifications, and graphical UI surfaces are not implemented and therefore have no screen IDs.
- Error output is specified as a state on every screen rather than as a separate error screen.

## Assumptions

- **A-002:** CLI commands are the applicable screen abstraction.
- **A-017:** A distinct command with its own inputs and JSON contract warrants a distinct screen ID even when it shares a handler family.
- **A-018:** `CORE-002` and `CORE-003` remain inventory surfaces despite the current root-help fallback because the parser exposes those groups and users must choose their leaf commands.

## Unresolved risks

- If the product direction changes to a GUI, the 29 IDs should be retained as capability trace IDs, not assumed to be a one-to-one page design.
- Some locally stored data lacks a corresponding read surface, so this inventory does not cover every database entity's lifecycle.
