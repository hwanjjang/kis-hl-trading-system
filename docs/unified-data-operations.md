# Unified data operations

The CLI stores canonical evidence, account/market fact revisions, coverage and
pinned journal/analysis results in the existing `data/kis_hl.sqlite`. It does not
submit orders. Raw payloads and exports remain private under ignored `data/`.
The [design](../specs/unified-trading-data.md) is the broader logical contract;
this implementation uses indexed `fact_revisions` with validated dataset payloads
instead of creating an unused physical table for every logical family.

## Initialize and inspect

```bash
python3 -m kis_hl.cli data migrate
python3 -m kis_hl.cli data migrate --apply
python3 -m kis_hl.cli data status
```

Migration preview does not create a database. Apply adds versioned canonical
schema without changing managed/trailing/eligibility tables. All commands retain
`--db` before the command name. Canonical connections use WAL, FULL synchronous
writes, foreign keys and bounded transactions; network calls run outside database
transactions. The database file is owner-readable/writable only.

`data status` lists account IDs/labels, revision counts, recent coverage, job
clocks and stale runs without printing native account identifiers. Registering a
parent does not select it for reports. `data journal` requires explicit account
IDs, so Master is excluded unless deliberately selected. Portfolio membership is
frozen as the selected account list per report; a separately editable portfolio
catalog is not implemented.

## Import existing raw evidence

Use an explicit private manifest, with paths relative to its directory:

```json
{
  "schema_version": 1,
  "accounts": [
    {"alias": "tradefi", "venue": "hyperliquid", "environment": "mainnet",
     "native_id": "REPLACE_WITH_ACTUAL_SUBACCOUNT", "label": "tradefi"}
  ],
  "files": [
    {"path": "fills.json", "sha256": "REPLACE_WITH_SHA256", "account": "tradefi",
     "role": "raw", "parser": "hl_fills"},
    {"path": "old-journal.json", "sha256": "REPLACE_WITH_SHA256", "role": "baseline"}
  ]
}
```

```bash
python3 -m kis_hl.cli data import --manifest data/import/manifest.json
python3 -m kis_hl.cli data import --manifest data/import/manifest.json --apply
```

Preview validates hashes, source paths, account scope, parser rows and conflicting
facts against the selected existing DB. It performs no DB migration. Repeated
imports preserve new source observations while effective facts remain unchanged.
Changed economics require `allow_correction: true` on the affected source entry;
previous revisions remain queryable. Parser preflight precedes economic writes.
Runtime failures may leave already committed evidence/facts; collection receipts
record failure and replay is idempotent. An interrupted `running` receipt is not
success. No manifest is marked applied until its import finishes.

Supported parsers:

| Parser | Source shape and contract |
| --- | --- |
| `hl_fills` | Native perpetual fill list; explicit USDC fees, startPosition and closedPnl; unresolved spot/collateral rejected |
| `hl_funding` | Native funding list; identity includes instrument/time/grain/hash; nSamples is a validated UTC-day aggregate |
| `kis_overseas_trans` | `output1` daily transaction rows; row currency, both-side commissions and settlement reconciliation |
| `kis_domestic_bundle` | `days`, `orders`, `costs_by_day_symbol`; profit rows, cumulative orders and symbol-scoped daily cost summaries must reconcile |
| `statement` | Explicit normalized source statement rows, described below |
| `evidence` | JSON preserved without inventing normalized trades |

Derived report JSON/CSV/SQLite files use role `baseline`; they are never additional
executions. Legacy imports preserve exact on-disk bytes as `legacy_json`. Native
HTTP collectors retain original response bytes; assembled/decoded data is labeled
`decoded_json`. Each observation records its payload digest and capture metadata.
Credential-bearing payloads are rejected, not silently scrubbed into fake raw data.

A normalized statement trade needs `source_id`, `instrument`, `currency`,
`event_start_ms`, `event_end_ms`, `time_precision`, `grain`, `side`, `quantity`,
`price`, `notional`, `total_cost` (or null), and a `costs` component object.
Financial values are decimal strings. Exact executions use MILLISECOND and the
half-open interval `[time,time+1)`; DAY statements retain their actual local day
interval. Do not put order timestamps into execution fields. Optional verified
`position_before` establishes sequence. KIS bundle normalization may establish a
unique path from the broker sell cost basis and day-end inventory. Ambiguous
paths stay pending. One summary shared by multiple orders requires a more precise
source allocation; the adapter does not guess.

KIS completed cycles require a source-backed `position_before: "0"` at the first
entry, or continuous reconciled inventory from an earlier anchored cycle. Import
this field only when the source establishes it; do not add it merely to finalize
a report. Complete trade-range coverage alone is insufficient. Without an anchor,
cycles carry `inventory_unanchored` and confirmed net returns remain unavailable.
The domestic bundle can supply this evidence through its existing reconciliation;
overseas DAY rows lacking inventory evidence remain pending. An inferred zero
balance does not establish a new anchor after unverified opening inventory.

A KIS sell exceeding tracked holdings records `opening_inventory_gap` before
closing any part of that row. DAY `day_end_quantity` is checked after all events
for that day, including sell/re-entry. Contradictory balances record
`ending_inventory_mismatch`. Affected cycles are excluded from completed-position
statistics; earlier verified cycles remain valid. Raw facts and observed fees are
retained, while an unreliable computed account net remains null. Inconsistent
inventory stops reconstruction of that instrument for the report; reconcile the
source and generate a new report to resume it.

Optional manifest `coverage` entries use `account`, `dataset` (`trade`/`cash`),
`start_ms`, `end_ms`, `status` and `details`. Complete coverage is an explicit
source-evidence assertion, not a conclusion from a short page. Use the actually
verified range, not an arbitrary lifetime span. Without complete coverage, cycle
return statistics remain pending; observed account totals still show their
coverage status.

## Read-only synchronization and scheduling

```bash
python3 -m kis_hl.cli data sync --venue hyperliquid --account ACTUAL_SUBACCOUNT --start-ms VERIFIED_START
python3 -m kis_hl.cli data sync --venue kis --start-ms VERIFIED_START
python3 -m kis_hl.cli data configure --job-id tradefi-history --config data/jobs/tradefi.json --interval-seconds 10800
python3 -m kis_hl.cli market collect --once
python3 -m kis_hl.cli market collect --poll-seconds 30
```

An account job JSON is `{"kind":"account","venue":"hyperliquid",
"account":"ACTUAL_SUBACCOUNT","start_ms":VERIFIED_START}`. KIS account selection
must match the configured account. Credentials use existing `.env` configuration.
Each run replays the configured range; use a bounded retained range for routine
polling and explicit older imports for historical audits. Attempts/success/next
due are distinct. A process lock serializes job runners; failures wait the
configured interval and remain visible in `collection_runs`.

KIS collection captures domestic profit/order summaries and US exchange
transaction statements. Other overseas markets require explicit source imports
or a reviewed adapter extension. DAY precision/coverage remain visible. HL
retained fills anchor execution coverage; funding pagination alone does not
certify lifetime funding completeness. Position responses are retained and HL
position rows normalized. Account cash valuation, transfers, dividends, corporate
action accounting, TWR/MWR and cross-currency capital returns are not inferred.

Configuration persists; **a running `market collect` process is required**.
Installing or supervising a persistent host service is separate from CLI setup.
No worker is automatically started by import, migration or configuration.

## Market history and sampling

```bash
python3 -m kis_hl.cli market backfill --instrument kis:069500 --timeframe 1w --years 10
python3 -m kis_hl.cli market backfill --instrument index:SPX --timeframe 1w --years 10
python3 -m kis_hl.cli market backfill --instrument hl:BTC --timeframe 1d
python3 -m kis_hl.cli market backfill --instrument hl:ETH --timeframe 1m
python3 -m kis_hl.cli market snapshot --instrument hl:xyz:SP500 --kind book
python3 -m kis_hl.cli market snapshot --instrument kis:SPY --kind quote
python3 -m kis_hl.cli market snapshot --instrument hl:BTC --kind funding
```

Weekly backfill defaults to ten calendar years, daily to two years, minute to
30 days. `--start`/`--end` accept ISO dates. Native weekly KIS pages move the date
cursor; HL returns only its retained candles. Available first/last timestamps,
missing completed weeks and provider limitations are recorded independently of
the request. Newer listings are never padded. OHLCV, provider, calendar,
adjustment, price basis and native/derived variant distinguish series; corrected
bars append revisions. Incomplete current bars stay out of completed-bar analysis.

KIS domestic minute history is limited to the current-day endpoint. KIS overseas
minute history uses bounded local-time pages; available retention remains partial. HL retains the latest
5000 candles for each interval. Those limits mean a 30-day minute or ten-year
weekly request may remain partial. Equity native session completeness is not
independently certified; raw source dates and missing-week candidates remain
visible. The pure weekly derivation API requires an explicit authoritative list
of expected sessions: it does not pretend weekdays form an exchange calendar.
Full empty weeks remain represented by coverage rather than fabricated OHLCV.

Market jobs use `kind: bar` with `instrument`, `timeframe`, `overlap_days` (14 by
default), or `kind: book/quote/funding` with `instrument`. Configure sampling at
60 seconds and funding at 3600 seconds as appropriate. KIS index books are not
supported. HL book/quote snapshots preserve top-of-book basis; they are not last
trade prices. Predicted funding and exhaustive tick/L2 streams are not collected.
Current realized funding polling overlaps the last two days.

## Journals and analysis

```bash
python3 -m kis_hl.cli data journal --accounts KIS_ACCOUNT_ID
python3 -m kis_hl.cli data journal --accounts TRADEFI_ACCOUNT_ID
python3 -m kis_hl.cli data journal --accounts KIS_ACCOUNT_ID TRADEFI_ACCOUNT_ID
python3 -m kis_hl.cli data export --report-id 1 --output data/reports/run-1.json
python3 -m kis_hl.cli data export --report-id 1 --output data/reports/run-1.html
python3 -m kis_hl.cli analysis run --spec data/analysis/weekly.json
```

Account IDs come from `data status`. Every result pins exact fact revisions,
dependency inputs, as-of time, account membership and calculation version. USD,
USDC and KRW remain separate. Closed-cycle net return divides net trading PnL by
entry notional; funding cashflow adds to gross PnL and trading fees subtract.
Builder fees are already included in HL total fees. Cost components are exposed
separately. Funding shared across cycles remains pending per cycle, and conflicting
daily/hourly representations are quarantined rather than double charged.
`net_booked_pnl` summarizes observed activity, including fees on open positions;
it is not a sum of finalized closed-cycle returns or a deposit-adjusted return.
New reports pin `inventory_policy_version: "kis-inventory-v1"` separately from the
unchanged metric formulas. Existing report IDs and exports remain immutable;
generate a new `data journal` run and export it to a new path to apply this policy.

The initial analysis supports a completed-bar close/mean summary. Its JSON spec
requires `instrument`, `provider`, `timeframe`, `adjustment`, `price_basis`,
`variant`, `calendar`, and optional `window` (20 default). `--as-of-ms` restricts
local knowledge and completed event time. Historical data first fetched today
cannot be claimed known to this store years ago. Corrections mark dependent
runs stale, including transitive derived inputs, without altering frozen results.
Future strategy skills can consume these manifests; no execution grants are
created by analysis.

Exports use a new JSON/HTML path, pending metadata, fsync and atomic rename,
followed by a ready digest. Existing paths and database targets are rejected.
After interruption, export the same frozen report ID to a new path; pending
artifacts are not published as ready. HTML is a readable escaped report, not an
interactive dashboard. Existing legacy journal/market commands still operate
on legacy tables; canonical consumers do not mix them into their totals. New
collection should use `data`/`market` commands. Historical legacy market tables
require an explicit source import; their overwritten revisions cannot be recovered.

## Backup, retention and rollout

```bash
python3 -m kis_hl.cli data backup --target /PERSISTENT_PRIVATE_PATH/kis-hl-backup.sqlite
python3 -m kis_hl.cli data restore --source /PERSISTENT_PRIVATE_PATH/kis-hl-backup.sqlite --target data/isolated-restore.sqlite
python3 -m kis_hl.cli data retention
```

Use a private persistent backup location outside ephemeral worktrees. Online
backup includes WAL contents consistently and writes a digest/integrity sidecar.
Restore requires a new isolated path and never replaces an existing database.
Run replay/reconciliation on the isolated copy before changing operational readers.
Do not replace the active DB after authoritative writes: repair forward.

Retention is preview-only, with deletion disabled. It shows unpinned minute
revisions older than 180 days and quote/book snapshots older than 30 days.
Account evidence and daily/weekly history are not auto-pruned. Dependencies of
pinned reports/analysis remain pinned transitively. Encryption/off-host transport
requires an operator-managed destination; credentials are not stored in backups.

Native Hyperliquid 1w boundaries observed on 2026-09-13 are Thursday UTC rather
than ISO Monday. Stored boundaries remain provider-native; weekly gap checks
validate the returned anchor. Cross-provider weekly comparisons must align
explicit intervals rather than assuming every `1w` label has the same boundary.

Recurring minute jobs use the last successful collection time minus a five-minute
overlap; the first run requests the latest 30 minutes. Failed runs preserve the
previous successful cursor. Explicit `market backfill --timeframe 1m` retains its
30-calendar-day request target. Instrument-local dates bound KIS requests, so a
Korean session after UTC midnight rollover is not clipped by the host timezone.


## Review correction workflows

`data status` and `data migrate` without `--apply` use read-only schema discovery.
They never create a missing database or apply schema changes. Explicit write
commands still initialize the additive schema when needed; `data migrate --apply`
is the dedicated initialization command. Preview checks the migration checksum.
The v1 DDL and historical checksums are unchanged.

KIS recurring account reads use a configurable `overlap_ms` (default one day)
before the last successful attempt. The initial run starts at `start_ms`. Configure
a second account job with `history_audit: true` and its own interval to replay the
older configured range. Its last_success_ms is the last successful audit time.
Partial collection does not advance the successful cursor. `worker_last_seen_ms`
is refreshed by each polling pass; a configured job is not proof of a running
worker. A blocked network request can age the heartbeat. No worker is installed or
started by these corrections.

KIS source snapshots with reconciled amounts may increase quantity/notional or
update settled fees. Earlier observations and fact revisions remain readable.
Decreases, incompatible representations and ambiguous repeated source rows require
explicit corrections. Domestic multiple-order buckets retain a day/side aggregate
and total fees with `shared_order_cost_allocation`; individual returns remain
pending. Valid other groups and US markets continue. Explicit import corrections
must be based on source evidence, not chosen to make a report look complete.

Canonical Hyperliquid public market collection is mainnet-only. Testnet/custom
endpoints are rejected before source capture; account sync retains its separate
network identity. Existing market rows with unknown network provenance are not
certified mainnet retroactively. Recollect from a verified source where provenance
matters. Index charts now require `price_basis: "index"`, `adjustment: "raw"` in
analysis specifications. Old mislabeled series remain historical evidence and are
not rewritten; recollect the correct series. New current analyses reject derived
bars with superseded daily inputs; rebuild the weekly variant first.

### Bounded independent-statement reconciliation

API pagination alone does not prove lifetime completeness. Obtain an independent
complete broker/exchange statement for a bounded half-open interval. Normalize its
rows to the documented adapter contract, preserve the original source externally,
and create a JSON document like this sanitized example:

```json
{
  "schema_version": 1,
  "source": "Broker statement export and normalization reference",
  "complete": true,
  "account": {"venue": "kis", "environment": "live", "native_id": "ACCOUNT"},
  "dataset": "trade",
  "start_ms": 0,
  "end_ms": 100,
  "parser": "statement",
  "rows": [],
  "opening_inventory": {},
  "closing_inventory": {}
}
```

Replace the example account, period, rows and inventories with actual evidence.
Rows use `statement`, `kis_overseas_trans` or `hl_fills` for trade; `hl_funding`
for cash. All records must lie fully within the interval and match the existing
canonical economic population, including provider-reported realized PnL, both-side fees or funding. Trade sources
must include opening and closing quantities for every represented instrument.
A source-backed flat opening quantity may anchor the first unambiguous event;
nonzero starting inventory still needs basis evidence and stays pending. A period
with no funding can be certified only from an independently complete empty funding
statement, never from an empty API response alone.

```bash
python3 -m kis_hl.cli data reconcile --statement data/statement.json --sha256 SOURCE_SHA256
python3 -m kis_hl.cli data reconcile --statement data/statement.json --sha256 SOURCE_SHA256 --apply
python3 -m kis_hl.cli data journal --accounts ACCOUNT_ID
```

The SHA-256 binds the supplied bytes; it does not authenticate the broker or prove
the operator's completeness declaration. Do not use a journal from this database
as independent evidence. Preview does not write. Apply repeats the checks in one
short SQLite transaction, retains source bytes and links coverage to exact fact
IDs. Corrections or newly discovered facts invalidate the certified population.
Late historical evidence flags affected reports for regeneration; prior exports
stay immutable. The original manifest coverage path remains a trusted operator
assertion for compatibility; prefer reconciliation for evidence-linked coverage.

For implemented versus outstanding broader-design acceptance, see
[the release acceptance ledger](unified-data-acceptance.md). Live transport,
account entitlements and historical depth were not exercised by the offline tests.


A recovered Hyperliquid gap segment records `invalidated_end_ms` at the new
source-backed flat anchor and remains PENDING, with no fabricated close execution.
Funding after that boundary belongs only to the recovered exposure. Summary
`unresolved_segments` is separate from currently open cycles. Journal freshness compares the current effective evidence population with
pinned inputs, so concurrent arrivals still trigger regeneration even if they
arrive while a historical as-of report is being calculated. Superseded old
revisions do not falsely invalidate a fresh report.
