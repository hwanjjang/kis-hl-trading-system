# Unified trading data specification

Status: broader design contract, partially implemented in PR #14. See [implemented/outstanding acceptance](../docs/unified-data-acceptance.md). Task: `unified-trading-data`. Authority: [intent](../intent/unified-trading-data.md). Evidence: [investigation](../reports/sdlc/unified-trading-data/investigation.md). Implementation sequence: [plan](../plans/unified-trading-data.md).

## 1. Storage decision and ownership — AC1

Keep `data/kis_hl.sqlite` as the authoritative local database, including operating state, source evidence, normalized account/market data and derived journal/analysis metadata. All commands resolve the same absolute path. SQLite remains the local state store; no database server, external message broker or web service is required.

“Raw” means unaltered source evidence, not cleaned values. Cleaning creates a new normalized revision with a source link. “Final” means eligible for a specific calculation at a specific revision, not an assertion that the vendor can never correct it.

Four logical layers share one database:

1. **Evidence:** immutable response bodies/import source objects, collection attempts, source row locators and coverage.
2. **Normalized facts:** instrument/account identities, executions or daily trade summaries, cash/cost events, position/balance snapshots and market observations.
3. **Reconciled projections:** position cycles, cost allocations, data-quality decisions and account/currency totals.
4. **Consumers:** journal reports, versioned analysis inputs/results and optional later strategy signals. HTML/CSV/JSON are reproducible exports.

Use compressed SQLite BLOBs for accepted JSON response bodies initially, content-addressed by SHA-256 of the original uncompressed bytes. Store encoding, codec, byte length and schema fingerprint. Small account/history volumes do not justify an external object store. Legacy imports retain the exact bytes available on disk and record `capture_format=legacy_json`; they must not claim the original HTTP byte representation. Authentication responses/headers never enter the raw store. Oversized future market payload archiving is a separate scaling change, not implicit filesystem dual-writing.

Private `data/`, backups, report exports, full account identifiers and raw payloads remain ignored by Git. Reusable collectors, schema migrations, validators and report generators move into versioned `kis_hl/` modules. Versioned tests use sanitized synthetic fixtures, never real account responses.

## 2. Identity, lineage and numeric conventions — AC2

- Accounts use stable IDs with unique `(venue, environment, native_account_id)`, optional `parent_account_id`, label and enabled datasets. An API key profile is a credential selector, not a different financial account. Master and subaccounts have different IDs. Registering a parent does not enable collection or reporting for it.
- Portfolios have effective-dated membership in `portfolio_members`. Initial membership is KIS and tradefi; Master remains excluded. Historical reports pin the membership revision.
- Instruments use stable listing/contract IDs with venue, market, exchange/DEX, native symbol, base/quote/settlement currencies and listing interval. Effective-dated `instrument_aliases` map provider symbols. Reuse the existing instrument catalog/mappings; an alias never performs a price or currency conversion.
- KOSPI/KOSPI200, 069500 and 122630; SPX, SPY/UPRO and `xyz:SP500`; NDX, QQQ/TQQQ and `xyz:XYZ100`; GLD and `xyz:GOLD`; KIS DRAM and `xyz:DRAM` remain distinct instruments connected by `reference_links`. Delisted/excluded assets remain journalable. Historical import cannot grant live eligibility.
- Money, quantity, prices, FX rates and return calculations use finite Decimal values serialized as canonical TEXT. Do not use SQLite REAL or implicit `SUM(TEXT)` coercion for financial aggregation. Keep currencies explicit; unknown cost is NULL with a reason, not zero.
- Facts carry `event_start_ms`, `event_end_ms`, `time_precision` (`MILLISECOND`, `SECOND`, `MINUTE`, `DAY`, `INTERVAL`, `UNKNOWN`), source date/timezone/calendar and `received_at_ms`. Store half-open coverage intervals. Do not turn an order timestamp or date-only row into an exact fill time.
- Every normalized revision has `source_observation_id`, row locator(s), adapter/version and transformation version. Every derived row has a calculation version and a manifest of exact upstream revision IDs. One fact may have multiple corroborating sources.
- Keep `source_available_at_ms` only when established, plus local `known_at_ms`. Corrected historical bars retain the time the correction became known. Backtests select only revisions known at the decision time or explicitly label retrospective research.

## 3. Logical schema and uniqueness — AC1, AC2

These are proposed table contracts, not executed DDL. Use additive migrations and a `schema_migrations(version, checksum, applied_at)` ledger. Foreign keys and NOT NULL/CHECK constraints enforce applicable scope, units and revisions; polymorphic reference validation belongs in the shared data-access boundary.

| Family / table | Essential fields and identity | Lifecycle |
| --- | --- | --- |
| `accounts`, `portfolios`, `portfolio_members` | Native account identity; effective-dated membership; configured enabled datasets | Version configuration changes; secrets external |
| `instruments`, `instrument_aliases`, `reference_links` | Native contract/listing identity; alias provider and validity interval; explicit reference relationship | Additive identities; no history loss on delisting |
| `raw_payloads` | `payload_id`, SHA-256, compressed bytes, codec, size, content/schema type | Immutable; identical byte bodies deduplicate |
| `collection_runs`, `source_observations` | Run, dataset, account/instrument, sanitized endpoint/parameters, requested range, provider clock, cursor, response digest, received time, outcome | Every attempt retained; identical payload at a later fetch is a new observation |
| `dataset_coverage` | Dataset + scope + source + grain + half-open range, status, reason, supporting run | Execution/cost/market coverage tracked independently |
| `fact_revisions`, `fact_sources` | Dataset, scoped business key, revision, normalized digest, supersedes ID, normalization version, source locators | Effective revision selected explicitly; conflicts quarantined |
| `account_orders` | Account + market + order date + native order ID + organization/exchange where needed; cumulative quantities/status | Order snapshots, never repeatedly counted as incremental fills |
| `account_trades` | Exact execution or statement-row identity; `grain=EXECUTION/ORDER_CUMULATIVE/DAY_SYMBOL_SIDE`, instrument, quantity, price/notional, chronology evidence | Incompatible grains cannot be summed together |
| `account_cash_events` | Account, currency, kind, signed actual cash delta, amount precision, effective interval, aggregation grain, native identity, linked trade or transfer | Funding, commission, tax, interest, rebate, deposit, withdrawal, dividend and transfer distinguished |
| `trade_cost_components` | Trade/fact revision, component kind, currency, positive expense/negative rebate, inclusion group, source field | Fees embedded in a cash/settlement amount identified as components, not a second debit |
| `account_position_snapshots`, `account_balance_snapshots` | Account, instrument/currency, observation time, quantity/cost basis, balance compartment, overlap/valuation semantics | Point-in-time evidence; not executions or deposits |
| `position_cycles`, `cycle_inputs`, `cost_allocations` | Account/instrument/cycle opening identity, revision, phase, source inputs, fee/funding attribution and allocation method | Rebuilt projections; revisions retained |
| `quality_findings`, `metric_eligibility` | Scope/revision, rule, severity, evidence, affected metric, resolution | Monetary PnL and holding-time eligibility independent |
| `market_bar_revisions` | Provider/instrument/timeframe/start/end/calendar/price basis/adjustment variant, revision, OHLCV, completion/coverage | Retain corrected/native/derived variants separately |
| `market_quote_snapshots`, `market_book_snapshots` | Provider/instrument, event and receive clocks, bid/ask/sizes or last/mark/oracle, sample interval, source revision | Sampled observations; not every exchange update |
| `market_funding_rate_revisions` | Provider/DEX/instrument, effective time/interval, actual/predicted classification, rate and revision | Market rate series, separate from account funding cash |
| `market_corporate_actions`, `market_fx_quotes` | Instrument/action/date/revision or currency pair/clock/source/rate convention | Supported facts only; unknown actions block affected reconstruction |
| `analysis_runs`, `analysis_inputs`, `analysis_results` | Purpose, strategy/code version, parameters, decision/as-of time, exact input revisions, metric version, outputs and quality | Reproducible, append-only runs |
| `journal_report_runs`, `report_artifacts` | Account/portfolio membership, as-of, metric versions, source/quality manifests, content digest, export status/path | Frozen reports and rebuildable exports |
| `ingestion_jobs`, `import_manifests` | Dataset scope, cadence, overlap, cursor, attempts/success times, resume state; file role/account/digest/parser | Local scheduler state; no credentials |

Indexes must support `(account_id, instrument_id, event_start_ms)`, `(account_id, currency, event_start_ms)`, `(dataset, business_key, revision)`, `(instrument_id, timeframe, start_ms, variant, known_at_ms)` and `(job_id, received_at_ms)`. Prevent an effective fact from having multiple active financial representations; enforce component/cash inclusion constraints transactionally.

Identity rules:

- Hyperliquid exact fill: account/environment + DEX/instrument + native `tid`; source hash is corroboration. Same identity and economic digest is idempotent. Different economics is an explicit correction/conflict.
- KIS: scope includes account/environment, market, broker order/trade date, organization/exchange, native ID and row grain. A daily statement without a transaction ID uses date/instrument/side/cash-credit classification plus documented grouping fields. Multiple indistinguishable rows remain unresolved; payload hash alone cannot declare them separate trades.
- Funding: zero/repeated hashes are not unique. Include account, instrument, event interval and granularity with source identity. If daily and hourly representations overlap, reconcile equivalence and choose one effective representation set. Merely adding granularity to the key would still double count; unresolved overlap is ineligible for full monetary totals.
- Re-fetching a daily aggregated cost after the vendor changes grouping creates a new observation and a replacement/equivalence decision, not another charge. Corrections mark dependent projections stale; old report manifests remain reproducible.

## 4. Acquisition and failure behavior — AC2

Fetch outside a write transaction. Capture body and sanitized request metadata, then commit observation + source reference. Normalize and promote validated facts in bounded transactions. Commit a verified page cursor only with its accepted observations. A failed normalization leaves raw evidence, a quality finding and a retryable cursor; it never certifies economic completeness.

Pagination tracks requested/returned ranges, row caps, cursor loops and provider retention anchors. A successful empty response means “no rows returned for this request”, not “no lifetime trading”. Coverage states are `COMPLETE_FOR_REQUEST`, `PARTIAL`, `UNAVAILABLE`, `FAILED`, with reasons such as pre-listing, retention boundary, unresolved grain or unsupported endpoint. Record requested versus actually covered periods and independently certify prices, quantities and costs.

Default account synchronization stays **10800 seconds**, configurable per account/dataset. Incremental reads use bounded overlap plus stable identity; overlap is a repair window, not a guarantee of old corrections. A separately configurable history-audit job revisits older segments and records last audited time. Explicit refresh/import can run on demand. A scheduling row alone is not proof that a process is running; expose heartbeat/next due/last attempt/last success separately. Manual HTS/web trades enter the same account facts; source interface remains unknown unless evidenced.

Retries apply only to safe reads and idempotent local imports. Never retry a signed trade through this ingestion pipeline. API errors, pagination exhaustion, schema drift, currency ambiguity, low disk space or `SQLITE_BUSY` leave a visible degraded dataset and preserve last good output. A report publishes new data only with its actual quality/coverage status.

## 5. Cost accounting, journals and analysis — AC3

For monetary reporting, use source authoritative realized PnL when its semantics are established, plus costs absent from that PnL exactly once:

`net = gross trading PnL - exchange/broker fee - builder fee - separately identified tax - interest + signed funding cashflow`

A source net number records `included_cost_kinds` and `accounting_basis`; never apply the full formula blindly to already-net PnL. Settlement cashflow is an independent reconciliation basis, not another PnL row. A discrepancy preserves both values, its cause/uncertainty and a quality decision.

- Hyperliquid `fee` includes `builderFee`: total trading fee is `fee`; exchange-only fee is `fee - builderFee`.
- KIS buy and sell costs must both be included. Domestic day/side summaries can split a same-day sell and re-entry when each side is uniquely attributable. Multiple orders without a unique allocation remain grouped/pending.
- Overseas KIS native-currency transaction settlements establish both-side costs; a sell-profit report alone may omit buy commission. Never infer a total's currency from an `frcr` prefix. Retain unclassified overseas charges instead of inventing a regulatory fee/tax split.
- Funding payment rows are signed cashflows; positive means received, negative paid. A historical daily aggregate is an interval. Allocate only to a uniquely overlapping supported cycle, or retain an exact group total and pending individual net returns. Net daily debits/credits do not claim gross hourly payments/receipts.
- A valid late statement can resolve allocation without deleting the original daily evidence. Allocations must conserve quantity and costs exactly, including partial exits and zero-crossing reversals. Reversal fees split by actual closed/open quantity; no cost is allocated twice.

Cycle phase (`OPEN/CLOSED`) is separate from quality. `monetary_status`, `chronology_status`, `cost_allocation_status`, `coverage_status` and per-metric eligibility avoid one global `FINALIZED` flag hiding useful information. KIS date-precision cycles may have reconciled net returns while the two exact elapsed holding-day statistics remain unavailable. Hyperliquid unresolved individual funding blocks individual net returns but can leave scoped group/account totals valid.

Keep the existing nine-statistic formula contract: net percentage returns, equal weight per completed cycle, breakeven excluded from decisive denominators, strategy-specific populations. Report numerator/denominator counts, excluded records and reasons for each metric. Exact holding days require actual endpoint timestamps; calendar-date differences are a distinct descriptive metric.

Net cycle return uses total entry notional, not current leverage/margin. Account booked trading PnL includes already settled costs on open positions and must be separated from completed-cycle PnL and current unrealized PnL. Analysis results always record the selected accounting population/basis.

Account equity, cash deposits and trading PnL are different datasets. Do not add overlapping unified spot/perp balance compartments. A capital-return module (TWR/MWR, drawdown/equity curve) is future gated analysis: it requires reconciled external cashflows, transfer pairs, valuation snapshots and currency policy. Transfers between included accounts are internal only after both legs are matched; a transfer to/from an excluded Master is external to that portfolio. Incomplete inputs produce unavailable capital returns. KRW, USD and USDC remain separate; optional translated reporting requires dated FX/USDC-USD quotes and a pinned conversion policy.

Strategy/indicator runs store code/skill version, parameters, indicator warm-up needs, completed-bar requirement and source revisions. Signals may reference these runs but cannot gain order authority from an analysis record. Revised market inputs create new analyses; they never rewrite the evidence used by an earlier decision.

## 6. Market-data profile and ten-year weekly history — AC4

Defaults below are proposed operational values, configurable by instrument/provider. Weekly ten-year history and inclusion of the selected data types are explicit user requirements; other cadence/retention numbers are tunable first-release defaults.

| Dataset | Target and initial history | Refresh / persistence |
| --- | --- | --- |
| Weekly OHLCV | Rolling **10 calendar years** by default, bounded by listing/provider history | After each completed market week; current week retained separately as provisional |
| Daily OHLCV | Two-year baseline; extend to ten years when needed to derive missing weekly history | After session close plus correction overlap; preserve imported history |
| Minute OHLCV | Base 1m; initial target 30 calendar days where available | Fetch recently closed bars about every minute during applicable market sessions |
| Derived bars | 9m / 3h when required by existing strategy; weekly from daily only under explicit calendar rules | Versioned derivation, input manifest and gap checks |
| Quote / top-of-book | Last/mark/oracle kept distinct; bid/ask and sizes | Default 60-second samples while market is active; cadence configurable |
| Market funding rates | Historical realized rates and optional predicted snapshots kept separate | Poll realized history hourly; predicted sampling opt-in |

A 10-year weekly target is a coverage objective, not a fixed “520 rows” test. ISO/calendar weeks, holidays, inception and delisting affect expected counts. Record `requested_start`, `available_start`, `available_end`, `listing_start`, expected completed intervals, missing intervals and source limitation. Do not fabricate pre-listing bars or forward-fill absent prices. The current unfinished week is excluded from completed-week statistics.

Prefer an explicit provider-native weekly series when available. If it is absent/incompatible, derive weekly OHLCV from a complete set of daily bars of the same instrument, provider, calendar and adjustment basis: first open, maximum high, minimum low, last close, summed compatible volume. Missing required daily sessions makes the week incomplete. If needed, extend daily backfill to support the ten-year weekly objective. Native and derived weekly series remain separate variants; discrepancy is recorded, never silently blended.

Calendar keys include timezone, session/calendar version, week anchor and interval convention. KRX uses its Korean trading calendar; US listings use their exchange/New York calendar including DST/holidays; 24/7 Hyperliquid contracts use a configured UTC week anchor. A HIP-3 contract and its cash-market reference retain their own calendars. Store interval start/end, provider label date and completion state, not just an ambiguous week number. Minute aggregation must respect gaps and session breaks. Historical UTC/cash-session bars are not silently substituted for the existing trailing worker's receive-time nine-minute policy.

Price basis (`TRADE`, `MARK`, `ORACLE`, `MID`, `INDEX`) and adjustment (`UNADJUSTED`, `SPLIT_ADJUSTED`, `TOTAL_RETURN`) are part of series identity. Never combine adjusted close with unadjusted O/H/L. Raw/unadjusted execution prices remain available for accounting. Unsupported split/redenomination transformations block affected reconstruction. Reference series are not converted to execution prices by alias.

Provider adapters must probe capabilities and paginate within documented/observed limits, using existing KIS/Hyperliquid clients and existing reference provider as an explicit fallback. The fallback records source, delay and licensing/quality status; it is not silently treated as primary exchange data. Account datasets are private/account scoped; public market observations are instrument scoped and reused across accounts without duplicating collection.

Retention: preserve account raw evidence, ledger revisions, reconciliations and report/analysis input manifests by default. Preserve weekly/daily series and revisions by default; ten years is a backfill target, not automatic deletion of older rows. For minute bars propose 180 days, quote/book snapshots 30 days, and replaceable market raw responses 30 days. First release implements retention preview only; deletion remains disabled until pin-aware archival/restore is tested. Any row/raw payload referenced by a retained report, analysis, unresolved finding or migration manifest is pinned transitively. Storage pressure pauses nonessential sampling and exposes the reason; it does not erase account evidence.

## 7. SQLite operation, export and backup — AC1, AC5

Use a shared connection factory: explicit foreign keys, bounded busy timeout, verified journal mode, supported runtime/schema checks and Decimal serialization. WAL is the proposed single-host mode, `synchronous=FULL` for durable financial writes. Verify runtime compatibility before enabling it. Fetch outside transactions, cap batches and yield market work between commits. Never claim WAL permits simultaneous writers.

Keep the current trading account locks and writer boundaries. No analytics query should hold a long write transaction. Proposed load gate: bounded market ingestion must add less than 250ms p95 to an isolated local supervisor-state write under the declared test workload, with no lost/reordered financial facts. Record measured hardware/workload; this is a target, not a measured guarantee. If it fails, reduce batch/cadence first; isolate market storage in another SQLite file only under a reviewed follow-up with explicit cross-file snapshot consistency. Do not use network filesystems or shared mutable DB copies across harness hosts.

DB publication and exports are separate durable steps: commit report metadata and exact source manifest; write HTML/CSV/JSON to a temp file; fsync/atomic rename; then mark the artifact ready with digest. Crash recovery resumes incomplete exports by report ID. A file is a derived artifact; it never becomes the authoritative account ledger.

Use SQLite's online backup facility for a consistent snapshot, with schema version, database digest, backup time and validation result. Keep backups outside ephemeral worktrees on a configured private persistent path. Filesystem permissions restrict raw data/DBs to the owner; credentials remain in existing config/token locations and are excluded from report exports. Encryption/off-host backup uses an operator-configured key and destination, not a credential stored inside the backup. Restore to an isolated path, run integrity/foreign-key checks and compare pinned report hashes/totals. Do not copy only the main file of a live WAL DB. Sources: [WAL](https://www.sqlite.org/wal.html), [backup API](https://www.sqlite.org/backup.html), [foreign keys](https://www.sqlite.org/foreignkeys.html).

## 8. Existing data migration and compatibility — AC5

1. Discover schema version/table families and resolve the absolute DB path. Empty today is not a precondition; later deployments may have live operating rows. Create a verified backup and import manifest before mutation.
2. Manifest identifies account/environment, source file role, hash, parser/version and capture precision. Import only declared raw evidence. Report HTML, derived CSV/JSON, source scripts and the separate report SQLite snapshots are retained as baselines, not ingested again as independent trades. Paths alone do not establish account identity; require discovery/config/source corroboration.
3. On an isolated copy, add new tables and import KIS/tradefi raw observations; register parent metadata without enabling Master. Deduplicate repeated pages and duplicate profile addresses. Normalize, reconcile positions/cash costs and rebuild projections. Preserve ambiguous funding groups and KIS DAY precision.
4. Compare per-account/per-currency quantities, actual fees/funding, settlement cashflows, coverage and quality flags against source evidence and frozen legacy reports. Explain every difference rather than forcing the new output to match a legacy error. Import again: effective facts/totals unchanged, repeated observation tracking allowed.
5. Preserve old table families through adapter reads and explicit schema versioning. Route legacy writers through the canonical layer when their domain switches; one domain must never have two independent authoritative writers. Unsupported old commands fail with a migration message rather than bypassing the canonical ledger. `market_daily_bars`/funding readers migrate to effective-version views without overwriting old rows. Existing managed/trailing tables stay operationally unchanged.
6. Cut over only at a controlled point: pause new entries, verify protection/recovery and stop affected writers; perform final additive migration/import on the **same** operational DB path. Reconcile live state before restarting. Do not switch locks to a report SQLite path. If safe coordination cannot be established, postpone cutover and retain the old functioning store.
7. Roll back readers/features while preserving new evidence. A pre-cutover DB restore is allowed only when there have been no later authoritative writes and all writers are stopped. After trading or financial writes resume, do not replace the DB with an old copy: use a forward repair or replay verified post-backup facts under reconciliation. Retain migration/run provenance.

Legacy map: `market_ticks/daily_bars/funding_rates/spread_snapshots` → versioned instrument observations; `journal_source_fills/cash_costs/sync_runs/cycles` → canonical account facts, components, coverage and projections; `trade_journal_entries` → explicitly marked manual legacy records with overlap review; private report DBs → export baselines; `managed_*`, `trailing_*`, order/protective tables → preserved operating state with optional fact links; eligibility tables → retained policy authority; existing `strategy_versions/signals` → reused IDs linked to analysis inputs.

## 9. Proposed CLI contracts and scope — AC6

Names below are design proposals, not commands currently available:

- `data status`: schema version, dataset coverage/quality, account identity, stale projections, scheduler heartbeat and storage size.
- `data migrate --dry-run`; `data import --manifest FILE --dry-run`: preview schema/import effects, conflicts and baseline comparison; a distinct apply operation is required during implementation rollout.
- `market backfill --profile default --timeframe 1w --years 10`: plan/collect achievable coverage and list gaps; weekly target independently configurable.
- `market collect --profile default --once`: collect due candles and sampled observations, without orders.
- Existing `journal sync/configure/report` gain canonical adapters and account/portfolio/as-of selection; existing 3-hour interval remains configurable.
- `analysis run --spec FILE --as-of TIME`: pin validated input revisions; `journal export --report-id ID` reproduces a frozen run.
- `data backup`, `data restore --target ISOLATED_PATH`, `data retention --dry-run`: explicit local maintenance with manifests.

## 10. Alternatives and outstanding validation

Rejected for the first release: merging report DB files as authoritative ledgers; destructive overwrite of raw data; immediate PostgreSQL/Timescale migration; permanent exhaustive tick/L2 capture; automatic cross-currency totals; deriving exact fill times from order times; forced allocation of ambiguous daily funding; generic perpetual-versus-index price aliases.

Implementation must prove pagination/retention for each provider, stable source row identity, correction invalidation, period-overlap representation selection, cash-cost conservation, weekly calendar construction, historical adjustment revisions, backup recovery and supervisor write latency. No load result, provider history guarantee, migration, scheduled collection or independent implementation verification is claimed by this design document.

## 2026-09-20 partial-cost correction — AC2, AC4, AC5, AC6

Portable statement costs are disjoint included components, including explicitly signed rebates. Fully known component sums must equal total_cost; supplied settlement must reconcile notional plus buy costs or minus sell costs. Contradictions reject import. If components contain null and their known sum differs from total_cost, preserve the statement as unresolved (including a positive remainder); do not infer the missing charge/credit from the difference, even if settlement agrees. New journal cycles and account/currency net totals remain pending/null and exclude unresolved cycles from confirmed statistics. Equal known sum or absent detail preserves the existing source-total contract; explicit signed components may resolve rebates. Recheck preexisting facts on report generation without rewriting old runs or raw evidence. Independent reconciliation must reject unresolved costs in either supplied rows or stored facts before changing anchors/coverage. No schema migration.

Backup must open an existing initialized source read-only. A missing or uninitialized source must not create a source DB, destination or sidecar. Existing online backup/restore behavior remains. Operator documentation states nonblocking runner lock rejection and live-only KIS statement routes. Broader-design status links to implemented/outstanding acceptance.
