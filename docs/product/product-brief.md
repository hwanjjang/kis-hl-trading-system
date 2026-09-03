# Product Brief

## Document status

- Product: KIS Hyperliquid Trading System
- Baseline: repository behavior on 2026-09-04
- Product shape: local, CLI-first operator tool
- Planning mode: current-state specification; this document does not authorize new functionality

## Product definition

The KIS Hyperliquid Trading System helps a technically capable trading operator collect and compare market data, inspect account state, evaluate a small set of deterministic signals, prepare or submit guarded Hyperliquid orders, and review completed trades from a traceable local record.

The product deliberately separates three concerns:

1. KIS and secondary-provider market data are reference inputs, not broker order routes.
2. Hyperliquid public data and signed trading use different trust levels.
3. Live execution is an explicit exception to the default dry-run workflow.

The current product is not a consumer trading application, hosted service, portfolio-management platform, or autonomous strategy daemon.

## Problem statement

A solo operator working across KIS, Hyperliquid, trade.xyz, and secondary market-data sources must otherwise resolve inconsistent symbols, inspect several data feeds, enforce asset and session policies manually, preserve evidence, and calculate trade-review metrics across disconnected tools. That creates avoidable execution, eligibility, and audit risk.

This product provides one local operating surface with explicit symbol resolution, curated asset eligibility, recent metadata verification, dry-run-first order preparation, structured JSON results, structured logs, and SQLite persistence.

## Target outcome

The operator can move from market-data refresh to a reviewed dry-run or guarded live action while being able to answer:

- Which instrument and venue name was resolved?
- Which data source and observation time informed the decision?
- Was the asset eligible and recently verified?
- For an applicable live order, was the underlying market session open, or was it explicitly overridden?
- Was an exchange action actually sent or only prepared?
- Where is the submission, protective-order, or completed-trade evidence stored?

## Primary users

- Primary: a solo trading operator who controls the local machine, configuration, wallet, and SQLite database.
- Supporting: a market-data analyst/operator who refreshes and reviews data without a signing key.
- Supporting: a strategy and risk reviewer who validates signals, exposure assumptions, and completed-trade metrics.
- Supporting: a maintainer/auditor who reviews logs, stored records, tests, and policy documentation.

These are operational personas, not application-enforced roles. See `personas.md`.

## In scope

### Configuration and local state

- Load non-secret runtime configuration from the repository `.env`.
- Select KIS sandbox/live credentials and Hyperliquid key profiles.
- Use a configurable local SQLite database, defaulting to `data/kis_hl.sqlite`.
- Emit JSON command results and structured logs.

### Market and account data

- Fetch KIS domestic or overseas quotes and overseas daily charts.
- Fetch Hyperliquid mids, candles, and wallet account state.
- Resolve user-facing spot, perpetual, and HIP-3 trade.xyz symbols.
- Collect trade.xyz universe, funding, top-of-book spread, mapped KIS quote, secondary quote, and daily OHLCV data.

### Asset governance

- Seed and list the curated trade.xyz eligibility map.
- Seed and list KIS and secondary-reference mappings.
- Detect new, missing, and unmapped live trade.xyz markets without making them tradable automatically.
- Store recent Hyperliquid metadata verification used by the live-order guard.

### Strategy and execution

- Evaluate the deterministic BTC perpetual 3-hour previous-high close breakout.
- Monitor BTC spot websocket mids and create a BTC perpetual entry/stop plan.
- Prepare Hyperliquid orders in dry-run mode by default.
- Submit allowlisted live orders only when `--live` is explicit and the applicable guards pass.
- Persist order submissions and reduce-only stop-market protective orders unless storage is disabled.

### Review

- Record one completed flat-to-flat position per journal record.
- Recalculate the nine required return-based review statistics, optionally filtered by symbol and strategy.

## Out of scope

- Graphical desktop, web, or mobile UI.
- Multi-user accounts, login, role-based access control, or cloud synchronization.
- KIS brokerage order submission.
- Fully autonomous trade.xyz strategy execution.
- Short-selling strategy rules beyond accepting manual short journal records.
- Automatic position/fill reconciliation, automatic journal creation, or restart reconciliation.
- Native trailing-stop orders or a completed application-level trailing daemon.
- Automatic funding/spread rejection, portfolio exposure caps, liquidation checks, or tick/lot rounding.
- Notifications, approvals, alerts, reports, scheduling, or remote administration.

## Core product principles

1. **Fail closed for live actions.** Unsupported assets, stale trade.xyz verification, missing credentials, and closed underlying sessions block applicable live entries.
2. **Dry-run first.** Absence of `--live` must never submit an exchange action.
3. **Evidence before automation.** Raw responses, checks, snapshots, and submissions are retained locally where implemented.
4. **Do not confuse reference data with execution.** KIS and Yahoo Finance inform review; only Hyperliquid is an execution venue.
5. **Eligibility is curated.** A newly observed market is not automatically approved for live trading.
6. **Machine-readable operation.** Successful commands return JSON; abnormal paths return a non-zero exit and a JSON error on stderr.

## Success measures

The current repository does not implement product analytics. The following are acceptance-oriented measures, not collected KPIs:

- Every supported CLI surface is represented once in `screen-inventory.md` and `screen-specs.md`.
- A dry-run order produces no signed exchange call.
- A live trade.xyz entry cannot pass without curated eligibility and recent successful metadata verification.
- Batch collection reports per-symbol success, skip, and failure without hiding partial results unless fail-fast is requested.
- Stored order, protective-order, market, and journal records retain enough identifiers and timestamps for local audit.
- Journal statistics follow the repository's nine-metric contract and preserve undefined values instead of inventing ratios.

## System context

| System | Product relationship | Trust/write level |
| --- | --- | --- |
| KIS Open API | Domestic/overseas/index reference market data | External read; credentials required |
| Hyperliquid `/info` and WebSocket | Public market/account state and signal inputs | External read; account address may be required |
| Hyperliquid signed exchange path | Order submission | External financial write; explicit `--live` and signing credentials required |
| Yahoo Finance chart API | Secondary reference quotes and daily bars | External read; not production-licensed execution data |
| Local SQLite | Eligibility, checks, market snapshots, submissions, protective orders, journal | Local read/write |
| `.env` and token cache | Runtime credentials and cached KIS tokens | Local sensitive state; never committed or printed intentionally |

## Dependencies and constraints

- Python 3.11 or newer and the repository dependencies are required.
- Network availability and upstream API behavior affect all external reads and live actions.
- SQLite is the only supported state store.
- The CLI has no interactive confirmation prompt; the operator reviews the generated command and dry-run output before adding `--live`.
- Dry-run output does not currently evaluate or include the underlying session decision; that guard runs only in the applicable live path.
- The product does not round prices or sizes to Hyperliquid tick/lot rules before submission.
- The BTC monitor uses process-local duplicate prevention and derives its stop from signal price rather than confirmed average fill.
- KIS commodity and FX mappings remain unsupported until exact routes are implemented.

## Evidence used

- Current repository: `README.md`, `docs/architecture.md`, `docs/strategy_execution_design.md`, `docs/trading_hours.md`, `docs/trade_xyz_assets.md`, `kis_hl/cli.py`, relevant domain modules, and tests.
- Reference repository: `flyingcop/backend` was reviewed only for documentation and operational-safety conventions; it is a different FLo shared-mobility product and contributes no trading requirements.
- Jira FY project: FY-5672 and FY-5673 were reviewed as examples of current-state product-document structure and traceability. Their rider-app requirements were not imported.

## Assumptions

- **A-001:** “This project” means the repository in the current workspace, `kis-hl-trading-system`; the linked FLo backend and FY Jira project are references, not the target product.
- **A-002:** “Screen” means a user-visible CLI command or command-group surface. No graphical screens are implied.
- **A-003:** The product is operated locally by one trusted OS user. Personas describe responsibilities, not separate authenticated accounts.
- **A-004:** Current code and tests take precedence over aspirational text where they disagree.
- **A-005:** Product acceptance covers deterministic behavior with stubbed external services; live exchange correctness remains an operational verification risk.
- **A-006:** Dates, market sessions, asset listings, upstream response shapes, and exchange limits are mutable external facts and require refresh before live use.

## Unresolved risks

- The requested Jira summary UI required browser login; the connected read-only Jira API supplied project and issue evidence instead.
- Live order behavior has not been exercised as part of this documentation task.
- A future GUI would require a separate product decision about authentication, roles, navigation, responsive behavior, and approval controls; none are inferred here.
- The current CLI can submit live orders without an interactive second confirmation after `--live` is supplied.
- Tick/lot rounding, exposure limits, fill reconciliation, and stop-placement compensation remain incomplete for unattended execution.
