# Screen Specifications

## Specification conventions

- A “screen” is a CLI surface listed in `screen-inventory.md` (A-002).
- Loading means the interval after command invocation and before final JSON/exit. The CLI generally provides no progress UI; structured logs may be visible.
- Permission restrictions describe actual credential, local file, and live-action gates. There is no application RBAC.
- Mobile behavior is “not supported” unless noted; a terminal on a phone receives the same text contract but has no responsive or touch-specific design.

## CORE-001 Command index

- **Screen purpose:** Discover global options and top-level commands.
- **Entry conditions:** Python environment and package entry point are available; invoke without a command or with help.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Program name, global `--db` option, top-level commands, command summaries, and argparse usage.
- **Primary actions:** Select a command; set a non-default SQLite path; request command help.
- **Empty state:** No command prints help and exits 2; this is the current empty-selection behavior.
- **Loading state:** None beyond process startup and environment/config loading.
- **Error state:** Parser errors print usage and an invalid-argument message, then exit 2.
- **Permission restrictions:** None at the index; downstream commands enforce local file, credential, or live-action requirements.
- **Mobile behavior:** No mobile UI; text may wrap in a mobile terminal.
- **Completion conditions:** The user identifies the exact next command and database target, or intentionally exits after reading help.

## MARKET-001 KIS quote result

- **Screen purpose:** Fetch one KIS domestic or overseas current quote and optionally retain the raw payload.
- **Entry conditions:** `kis-price` with `--market` and `--symbol`; applicable KIS credentials; exchange/market code defaults reviewed.
- **User roles:** P-01, P-02, P-04.
- **Displayed data:** HTTP/status value, raw KIS response body, and optional `stored_id`.
- **Primary actions:** Choose domestic/overseas; enter symbol; override code; add `--store`.
- **Empty state:** A successful upstream body may contain no quote; it is shown as received rather than replaced by UI copy.
- **Loading state:** No final JSON until token/auth and quote request finish; structured logs may show retry context.
- **Error state:** HTTP failure or KIS body failure raises; JSON `error` is written to stderr and process exits 1 without a successful stored row.
- **Permission restrictions:** Valid KIS app credentials are required; local database write permission is additionally required for `--store`.
- **Mobile behavior:** No mobile-specific input controls or response formatting.
- **Completion conditions:** A successful response is printed and, if requested, its raw payload has a returned local ID.

## MARKET-002 KIS overseas daily chart result

- **Screen purpose:** Fetch an overseas daily/weekly/monthly chart response for a symbol and date interval.
- **Entry conditions:** `kis-daily` with symbol, `--from`, and `--to`; valid KIS credentials; period and market code reviewed.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Status, raw chart response body, and optional `stored_id`.
- **Primary actions:** Set symbol/date bounds; override period/market code; opt into storage.
- **Empty state:** An upstream success with no bars is returned as an empty body/list according to KIS schema.
- **Loading state:** Synchronous request with no dedicated progress indicator.
- **Error state:** Invalid dates are passed to the upstream contract; request/body failure returns stderr JSON and exit 1.
- **Permission restrictions:** KIS credentials and network access; database write permission when storing.
- **Mobile behavior:** No date picker or mobile validation; dates are typed as command arguments.
- **Completion conditions:** The requested raw chart response is visible and optional persistence is acknowledged.

## MARKET-003 Hyperliquid mids result

- **Screen purpose:** Read all mids for the selected dex or a resolved subset of symbols.
- **Entry conditions:** `hl-mids`; optional `--dex`; optional zero or more `--symbols`.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** All returned mids, or filtered `mids` plus each resolved asset and its order coin.
- **Primary actions:** Select dex; request specific symbols; inspect spot/perp/HIP-3 resolution.
- **Empty state:** No returned markets produces an empty `mids` object; a missing requested mid is represented as null.
- **Loading state:** Synchronous public `/info` call; spot metadata may add a second call for unresolved spot order coin.
- **Error state:** Transport, response-shape, symbol-resolution, or spot-meta failure returns stderr JSON and exit 1.
- **Permission restrictions:** No wallet/private key required; network access is required.
- **Mobile behavior:** Large JSON may require horizontal/vertical terminal scrolling; no responsive summarization.
- **Completion conditions:** Returned values are associated with explicit resolved identities.

## MARKET-004 Hyperliquid candle result

- **Screen purpose:** Fetch a candle snapshot for one resolved market and time range.
- **Entry conditions:** `hl-candles` with symbol, start/end milliseconds; optional interval and dex.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** `candles` array using the upstream candle fields.
- **Primary actions:** Set symbol, interval, time bounds, and dex.
- **Empty state:** `candles: []` when the upstream call succeeds with no observations.
- **Loading state:** Synchronous public `/info` call without progress feedback.
- **Error state:** Invalid symbol/range, transport, or upstream response errors produce stderr JSON and exit 1.
- **Permission restrictions:** No signing credentials required; network access required.
- **Mobile behavior:** Raw candle arrays are not condensed for small terminals.
- **Completion conditions:** The requested snapshot is returned, including an explicit empty result when applicable.

## ACCOUNT-001 Hyperliquid account state

- **Screen purpose:** Aggregate the funded account's main perpetual, optional spot, and optional HIP-3 states.
- **Entry conditions:** `hl-account`; a valid explicit `--user` or configured account address.
- **User roles:** P-01, P-03, P-04.
- **Displayed data:** User address, main perp state, optional spot state, named dex states, and optional ALL_DEXES aggregate.
- **Primary actions:** Override user; repeat `--dex`; suppress spot; request ALL_DEXES where supported.
- **Empty state:** Valid accounts with no balances/positions retain the upstream empty collections; an API-wallet address can misleadingly appear empty.
- **Loading state:** Sequential public account-state requests; no partial final report until the composite call returns.
- **Error state:** Missing address, transport failure, or unavailable optional aggregate returns stderr JSON and exit 1.
- **Permission restrictions:** Account address required; no private key required because reads use `/info`.
- **Mobile behavior:** Nested JSON is unchanged and may be difficult to scan on a small terminal.
- **Completion conditions:** The output names the queried address and contains all requested account partitions.

## ASSET-001 Hyperliquid symbol resolution

- **Screen purpose:** Preview how a user-facing symbol maps to Hyperliquid coin, kind, dex, and explanatory note.
- **Entry conditions:** `resolve-symbol --symbol`; optional dex.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Resolved coin, asset kind, dex, and note.
- **Primary actions:** Enter an alias; compare spot, perpetual, and `xyz:` forms before another command.
- **Empty state:** None; symbol is required and a valid resolution always returns a record.
- **Loading state:** Immediate local computation; no network request.
- **Error state:** Unsupported/invalid symbol returns stderr JSON and exit 1.
- **Permission restrictions:** None beyond local execution.
- **Mobile behavior:** Same small JSON response in any terminal.
- **Completion conditions:** One unambiguous resolved identity is returned or the input is rejected.

## STRATEGY-001 BTC 3-hour breakout evaluation

- **Screen purpose:** Evaluate the implemented BTC perpetual previous-high close breakout independently of order execution.
- **Entry conditions:** `btc-3h-breakout` with start/end milliseconds; optional supported BTC perpetual alias and positive lookback.
- **User roles:** P-01, P-03, P-04.
- **Displayed data:** Signal dataclass fields, including symbol/resolved coin, interval, prior breakout level, latest close, lookback, and `should_enter`.
- **Primary actions:** Select time range and lookback; review the boolean and evidence.
- **Empty state:** Insufficient candles are an error, not a neutral signal; a valid non-breakout returns `should_enter=false`.
- **Loading state:** Synchronous candle fetch and local evaluation; no progress UI.
- **Error state:** Invalid lookback/candle data or external failure returns stderr JSON and exit 1.
- **Permission restrictions:** Public Hyperliquid read only; no signing key and no live-action permission required.
- **Mobile behavior:** Same JSON; no chart visualization.
- **Completion conditions:** A deterministic signal result is printed and no order has been sent.

## STRATEGY-002 BTC breakout monitor

- **Screen purpose:** Build closed 3-hour BTC spot candles from a maintained stream and prepare or submit a BTC perpetual entry plus protective stop after a breakout.
- **Entry conditions:** `btc-3h-monitor`; valid explicit ATR or retrievable daily candles; network; reviewed sizing/stop parameters; `--live` only for intended external actions.
- **User roles:** P-01; P-03 reviews; P-04 tests with dry-run/stubs.
- **Displayed data:** Final websocket status, ATR, entry notional, stop multiple, and zero or more execution objects with entry/stop results and stored IDs.
- **Primary actions:** Override ATR/lookback/notional/stop/slippage; bound messages/reconnects; disable storage; explicitly enable live mode.
- **Empty state:** A completed/stopped monitor with no breakout returns an empty `executions` list.
- **Loading state:** Long-running stream; final JSON is delayed until stop/limit/termination. Structured connection logs are the only interim feedback.
- **Error state:** ATR, stream, resolution, guard, entry, stop, or persistence error can terminate with stderr JSON and exit 1; reconnect behavior is bounded by runner options.
- **Permission restrictions:** Dry-run needs no signing key; live mode requires allowlisted BTC perpetual, account/private key, and exchange acceptance. Local writes require database permission.
- **Mobile behavior:** No background-service, notification, or touch controls; terminal suspension may terminate monitoring.
- **Completion conditions:** Monitor status is returned and every generated execution is explicitly marked dry-run/submitted with available persistence IDs.

## ORDER-001 Hyperliquid order preparation/submission

- **Screen purpose:** Resolve, validate, preview, and optionally submit one supported Hyperliquid limit, market, or reduce-only stop-market order.
- **Entry conditions:** `trade` with symbol, side, type, and size; price for limit; trigger plus reduce-only for stop-market; `--live` only after review.
- **User roles:** P-01; P-03 reviews; P-04 tests dry-run.
- **Displayed data:** Status, dry-run flag, resolved asset, normalized request, exchange/skipped response, timestamp, optional stored and protective IDs; session context appears only when evaluated for an applicable live non-reduce-only order.
- **Primary actions:** Choose parameters; run default dry-run; repeat with `--live`; use explicit session override only as an exception; disable storage if intentionally needed.
- **Empty state:** None; required order intent must be supplied. A dry-run uses a structured skipped response rather than a blank result.
- **Loading state:** Local validation/resolution, plus metadata/spot/session/SDK work in applicable live paths; no interactive confirmation or progress UI.
- **Error state:** Invalid parameter combination, unsupported asset, stale verification, missing credentials, closed session, spot-meta failure, exchange rejection, or storage error returns stderr JSON and exit 1.
- **Permission restrictions:** Live signed writes require explicit `--live`, allowlisted asset, recent verification for trade.xyz, wallet/private key, and session compliance or explicit override. The CLI has no RBAC.
- **Mobile behavior:** No order ticket or confirmation modal; command-line review is the only presentation.
- **Completion conditions:** Dry-run ends with `dry_run=true` and no exchange action; live success ends with `submitted` evidence and default local persistence.

## CORE-002 Journal command index

- **Screen purpose:** Introduce completed-trade entry and statistics report operations.
- **Entry conditions:** Invoke `journal` without a leaf command or request help.
- **User roles:** P-01, P-03, P-04.
- **Displayed data:** Current implementation falls back to root help when no handler is selected; explicit help exposes child parsers through argparse.
- **Primary actions:** Choose `add` or `stats`.
- **Empty state:** No child selection prints help and exits 2.
- **Loading state:** None.
- **Error state:** Unknown child or invalid syntax produces argparse error and exit 2.
- **Permission restrictions:** None at the group index.
- **Mobile behavior:** Text-only help; no mobile adaptation.
- **Completion conditions:** The user selects JOURNAL-001 or JOURNAL-002, or exits after help.

## JOURNAL-001 Completed trade entry result

- **Screen purpose:** Store one fully closed flat-to-flat position and show its current statistics snapshot.
- **Entry conditions:** `journal add` with symbol, side, open/close timestamps, entry/exit price, and quantity; weighted averages used for partial fills; position fully flat.
- **User roles:** P-01 enters; P-03 reviews; P-04 verifies.
- **Displayed data:** Stored ID, normalized journal entry, nine statistics, and required-statistic names.
- **Primary actions:** Supply venue/strategy/costs/authoritative realized PnL/legacy outcome/notes as needed.
- **Empty state:** None; a completed-trade record requires all core fields. Zero PnL is a visible breakeven record.
- **Loading state:** Local validation, read of existing entries, recalculation, and SQLite insert; normally immediate.
- **Error state:** Invalid times, decimals, sides, or record contract; database failure returns stderr JSON and exit 1.
- **Permission restrictions:** Local database write permission; no external service or trading credential required.
- **Mobile behavior:** Long notes and timestamps are typed arguments; no mobile form safeguards.
- **Completion conditions:** One record is stored, its ID is returned, and metrics reflect the population including the new record.

## JOURNAL-002 Trade statistics report

- **Screen purpose:** Recalculate current completed-trade metrics and list the selected entries.
- **Entry conditions:** `journal stats`; optional exact symbol and/or strategy filters; readable SQLite path.
- **User roles:** P-01, P-03, P-04.
- **Displayed data:** Applied filters, nine statistics, and raw selected entries.
- **Primary actions:** Filter by symbol/strategy; compare strategy-specific populations.
- **Empty state:** No matching entries returns an empty list and null/zero values according to the metric contract; undefined ratios remain null.
- **Loading state:** Local SQLite read and Decimal calculations; no progress UI.
- **Error state:** Database/schema/read failure returns stderr JSON and exit 1.
- **Permission restrictions:** Local read permission only; no exchange credentials.
- **Mobile behavior:** Large entry arrays are not paginated or summarized for mobile terminals.
- **Completion conditions:** Metrics are derived from exactly the returned filter population.

## CORE-003 trade.xyz asset command index

- **Screen purpose:** Introduce asset, verification, market-evidence, mapping, and history operations.
- **Entry conditions:** Invoke `xyz-assets` without a leaf command or request help.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Current no-handler behavior falls back to root help; command help enumerates leaf operations.
- **Primary actions:** Select a seed, list, verify, collect, or mapped-fetch operation.
- **Empty state:** No child selection prints help and exits 2.
- **Loading state:** None.
- **Error state:** Unknown child/argument produces argparse error and exit 2.
- **Permission restrictions:** None at the index; leaf commands vary.
- **Mobile behavior:** Text-only command discovery.
- **Completion conditions:** A leaf surface is selected or help has answered the navigation need.

## ASSET-002 Seed curated asset map

- **Screen purpose:** Create or refresh SQLite rows from the code-owned curated trade.xyz seed.
- **Entry conditions:** `xyz-assets seed`; writable database path.
- **User roles:** P-02, P-04; P-01 may initialize local state.
- **Displayed data:** Seeded row count and database path.
- **Primary actions:** Run against the exact database intended for verification/orders.
- **Empty state:** A zero count is displayed if the seed contains no rows; no empty-state copy.
- **Loading state:** Local schema initialization/upsert; normally immediate.
- **Error state:** Database path/schema/write failure returns stderr JSON and exit 1.
- **Permission restrictions:** Local file/database write permission; no network or API credentials.
- **Mobile behavior:** Supported only through a capable terminal with access to the same local files.
- **Completion conditions:** Seed count is returned and rows are readable from the chosen database.

## ASSET-003 Curated asset list

- **Screen purpose:** Review curated trade.xyz eligibility and optional class/tradable filters.
- **Entry conditions:** `xyz-assets list`; database initialized or readable.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Count and asset rows including mapping/eligibility fields.
- **Primary actions:** Filter to tradable rows; filter by asset class.
- **Empty state:** `count: 0` and `assets: []` for an unseeded database or unmatched filter.
- **Loading state:** Local SQLite read; immediate in normal use.
- **Error state:** Database/schema/read failure returns stderr JSON and exit 1.
- **Permission restrictions:** Local read access only.
- **Mobile behavior:** No pagination; large lists scroll as raw JSON.
- **Completion conditions:** The returned count matches the listed rows and requested filters.

## ASSET-004 Hyperliquid metadata verification

- **Screen purpose:** Compare curated assets with live Hyperliquid `xyz` mids and store checks used by live-order freshness policy.
- **Entry conditions:** `xyz-assets verify`; seeded asset map; network; optional class; excluded rows included only with `--all`.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Database path, summary counts, and per-asset availability/check details.
- **Primary actions:** Verify tradable rows; include excluded rows for audit; filter by class.
- **Empty state:** No selected curated rows returns zero counts and an empty checks list.
- **Loading state:** One public mids request followed by local per-row verification/storage; no progress UI.
- **Error state:** Network/shape/database failure returns stderr JSON and exit 1; unavailable assets are represented as failed checks rather than silently omitted.
- **Permission restrictions:** Public Hyperliquid network access and local database write permission; no signing key.
- **Mobile behavior:** No mobile freshness indicator; timestamps and booleans remain raw JSON.
- **Completion conditions:** Every selected row has a visible check result persisted to the same database.

## ASSET-005 Live trade.xyz universe snapshot

- **Screen purpose:** Snapshot current `xyz` universe and expose new, missing, and unmapped symbols without changing eligibility.
- **Entry conditions:** `xyz-assets universe-collect`; network; optional writable database unless `--no-store`.
- **User roles:** P-02, P-03, P-04.
- **Displayed data:** Snapshot/database IDs, asset and context coverage counts, new/missing/unmapped symbol arrays, and stored flag.
- **Primary actions:** Collect/store a snapshot; run read-only with `--no-store`; review deltas.
- **Empty state:** Empty universe is either a valid zero-count result if structurally valid or a response-shape error if required fields are absent.
- **Loading state:** Public metadata/context request and optional SQLite writes; no progress UI.
- **Error state:** Missing universe/contexts, transport, or storage error returns stderr JSON and exit 1.
- **Permission restrictions:** Public Hyperliquid read; local write permission only when storing.
- **Mobile behavior:** Symbol arrays display as raw JSON; no badges or diff visualization.
- **Completion conditions:** Current universe counts/deltas are returned and optional snapshot ID confirms storage.

## ASSET-006 Funding history collection

- **Screen purpose:** Collect per-symbol trade.xyz funding history over a defined lookback.
- **Entry conditions:** `xyz-assets funding-collect`; network; symbols or a resolvable current universe; positive lookback expected.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Database, lookback, requested/succeeded/failed/stored-row totals, and per-symbol latest rate/premium or error.
- **Primary actions:** Bound symbols/time; delay requests; disable storage; enable fail-fast.
- **Empty state:** A symbol with no rows is a success with zero rows and null latest values; no resolved symbols yields zero summary/list.
- **Loading state:** Sequential per-symbol calls with optional delay; final JSON only after the batch.
- **Error state:** Default captures a per-symbol failure and continues; `--fail-fast` or pre-loop resolution failure exits 1.
- **Permission restrictions:** Public Hyperliquid read; local write permission when storage enabled.
- **Mobile behavior:** No incremental batch progress UI or mobile table.
- **Completion conditions:** Every requested symbol appears once in results and summary counts reconcile.

## ASSET-007 Spread snapshot collection

- **Screen purpose:** Collect top-of-book bid/ask, mid, absolute spread, spread bps, and sizes for selected trade.xyz markets.
- **Entry conditions:** `xyz-assets spread-collect`; network; symbols or resolvable universe.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Requested/succeeded/failed/stored totals and per-symbol spread snapshot or error.
- **Primary actions:** Bound symbols; delay; disable storage; choose fail-fast.
- **Empty state:** No resolved symbols returns a zero summary; empty bid/ask levels are errors, not zero spreads.
- **Loading state:** Sequential order-book calls and optional writes/delays; no interim result table.
- **Error state:** Invalid/empty/crossed book is a per-symbol failure by default; fail-fast exits 1.
- **Permission restrictions:** Public Hyperliquid read and local write when enabled.
- **Mobile behavior:** Raw numeric strings; no compact spread chart.
- **Completion conditions:** Each requested symbol has a success snapshot or explicit failure, with reconciled counts.

## KISMAP-001 Seed KIS mappings

- **Screen purpose:** Initialize/refresh curated routes from trade.xyz symbols to supported, excluded, or unsupported KIS market data.
- **Entry conditions:** `xyz-assets seed-kis`; writable database.
- **User roles:** P-02, P-04; P-01 may initialize.
- **Displayed data:** Seeded count and database path.
- **Primary actions:** Seed the same database used by mapped fetch/collect.
- **Empty state:** Zero seeded rows is shown directly.
- **Loading state:** Local schema/upsert only.
- **Error state:** Database write/schema failure returns stderr JSON and exit 1.
- **Permission restrictions:** Local write permission; no KIS credentials needed to seed.
- **Mobile behavior:** Terminal-only local operation.
- **Completion conditions:** Count returned and mappings are available to KISMAP-002 through KISMAP-004.

## KISMAP-002 KIS mapping list

- **Screen purpose:** Review KIS route coverage and reasons for unsupported/excluded assets.
- **Entry conditions:** `xyz-assets kis-list`; readable initialized database.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Count and mapping rows.
- **Primary actions:** Filter by status and KIS market route.
- **Empty state:** Zero count and empty mappings for unseeded or unmatched filters.
- **Loading state:** Local SQLite read.
- **Error state:** Database/schema/read error returns stderr JSON and exit 1.
- **Permission restrictions:** Local read only.
- **Mobile behavior:** Raw list without pagination or responsive columns.
- **Completion conditions:** Output rows match selected status/market filters.

## KISMAP-003 Mapped KIS quote result

- **Screen purpose:** Fetch one KIS observation using an existing active trade.xyz route.
- **Entry conditions:** `xyz-assets kis-fetch --symbol`; mapping exists and is active; KIS credentials; optional storage.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Mapping, response status/body, and optional stored ID.
- **Primary actions:** Select trade symbol; opt into storing the raw response.
- **Empty state:** A successful empty upstream body is displayed; missing mapping is an error.
- **Loading state:** Mapping lookup, token/auth, route-specific KIS call, optional write.
- **Error state:** Missing/inactive mapping, unsupported route, KIS body/HTTP error, or persistence failure exits 1.
- **Permission restrictions:** KIS credentials/network; local write permission only with `--store`.
- **Mobile behavior:** No symbol picker or mapping detail layout.
- **Completion conditions:** Active route and source response are shown together; optional storage ID returned.

## KISMAP-004 Mapped KIS quote batch

- **Screen purpose:** Collect KIS quotes for active mappings while reporting skipped and failed symbols.
- **Entry conditions:** `xyz-assets kis-collect`; seeded mappings; KIS credentials; optional symbols.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Database; requested/succeeded/failed/skipped/stored totals; per-symbol route, last price, response status, stored ID, reason, or error.
- **Primary actions:** Bound symbols; delay requests; disable default storage; enable fail-fast.
- **Empty state:** No resolved mappings yields zero totals and empty results.
- **Loading state:** Sequential route-specific KIS calls with optional delay; retries may extend duration.
- **Error state:** Inactive mappings are skipped; per-symbol errors continue by default; fail-fast exits 1.
- **Permission restrictions:** KIS credentials/network for active rows; local write permission when storing.
- **Mobile behavior:** No progress notification or paginated result view.
- **Completion conditions:** Every resolved mapping has one result and all summary totals reconcile.

## REFMAP-001 Seed secondary mappings

- **Screen purpose:** Initialize/refresh curated secondary-provider routes for trade.xyz references.
- **Entry conditions:** `xyz-assets seed-ref`; writable database.
- **User roles:** P-02, P-04; P-01 may initialize.
- **Displayed data:** Seeded count and database path.
- **Primary actions:** Seed the intended operational database.
- **Empty state:** Zero seeded rows is displayed.
- **Loading state:** Local schema/upsert only.
- **Error state:** Database write/schema error returns stderr JSON and exit 1.
- **Permission restrictions:** Local write only; no provider credential currently required.
- **Mobile behavior:** Terminal-only operation.
- **Completion conditions:** Mapping count returned and rows are available to downstream reference commands.

## REFMAP-002 Secondary mapping list

- **Screen purpose:** Review provider, symbol, class, and active/excluded secondary routes.
- **Entry conditions:** `xyz-assets ref-list`; readable initialized database.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Count and mapping rows.
- **Primary actions:** Filter by provider, status, or asset class.
- **Empty state:** Zero count and empty mappings when no rows match.
- **Loading state:** Local database read.
- **Error state:** Database/schema/read failure returns stderr JSON and exit 1.
- **Permission restrictions:** Local read only.
- **Mobile behavior:** Raw JSON list; no pagination.
- **Completion conditions:** Returned rows match all selected filters.

## REFMAP-003 Mapped secondary quote result

- **Screen purpose:** Fetch one secondary quote using an active trade.xyz reference mapping.
- **Entry conditions:** `xyz-assets ref-fetch --symbol`; active mapping; network; optional range/interval and storage.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Mapping, provider response status/body, and optional stored ID.
- **Primary actions:** Select symbol/range/interval; opt into storage.
- **Empty state:** Valid provider response with no observation is displayed; missing/inactive mapping is an error.
- **Loading state:** Mapping lookup, provider request, optional database write.
- **Error state:** Mapping, provider transport/schema/rate-limit, or storage failure returns stderr JSON and exit 1.
- **Permission restrictions:** Network access; local write permission when storing; no trading permission.
- **Mobile behavior:** No chart or provider-aware mobile presentation.
- **Completion conditions:** Mapping and source response remain visibly linked, with optional stored ID.

## REFMAP-004 Mapped secondary quote batch

- **Screen purpose:** Collect secondary quotes for active mappings with per-symbol outcome reporting.
- **Entry conditions:** `xyz-assets ref-collect`; seeded mappings; network; optional provider/class/symbol filters.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Database; requested/succeeded/failed/skipped/stored totals; per-symbol provider data or cause.
- **Primary actions:** Filter; choose range/interval; delay; disable storage; enable fail-fast.
- **Empty state:** No selected mappings produces zero totals and empty results.
- **Loading state:** Sequential external calls with optional delays; final report after batch.
- **Error state:** Inactive rows skip; per-symbol failures continue by default; fail-fast exits 1.
- **Permission restrictions:** Network and optional local write; no KIS or exchange signing credentials.
- **Mobile behavior:** No progress UI, pagination, or compact table.
- **Completion conditions:** Each resolved mapping has one visible result and totals reconcile.

## HISTORY-001 Daily OHLCV collection

- **Screen purpose:** Fetch and idempotently store daily bars needed for ATR/trend review across tradable trade.xyz assets.
- **Entry conditions:** `xyz-assets daily-collect`; network; positive day range; optional symbols/class/end date. The command seeds eligibility and reference mappings before route resolution.
- **User roles:** P-01, P-02, P-03, P-04.
- **Displayed data:** Database, collection window, requested/succeeded/failed/skipped/stored-row totals, routes, and per-symbol results/errors.
- **Primary actions:** Bound symbols/class/days/exclusive end date; delay; disable storage; enable fail-fast.
- **Empty state:** No eligible selected routes yields zero totals; a successful symbol with no bars reports zero rows rather than fabricated data.
- **Loading state:** Route resolution plus sequential Yahoo chart calls and optional upserts/delays; no progress surface.
- **Error state:** Invalid ISO date, unavailable/inactive route, provider error, normalization failure, or database error is per-symbol unless fail-fast or pre-loop validation exits 1.
- **Permission restrictions:** Network and optional local write; no live trading credentials.
- **Mobile behavior:** No date picker, progress notification, or OHLC chart.
- **Completion conditions:** Every selected route is accounted for and successful stored rows are ready for downstream ATR/trend calculations.

## Assumptions

- **A-002:** CLI surfaces satisfy the requested screen abstraction.
- **A-019:** “Displayed data” means the final JSON contract plus argparse help; structured logs are supporting diagnostics.
- **A-020:** “Permission” includes credentials, network access, and filesystem/database access because no authenticated user model exists.
- **A-021:** Mobile behavior documents the current absence of a mobile UI and does not promise support for mobile terminal operation.
- **A-022:** Upstream successful-but-empty payload semantics are preserved unless current code explicitly promotes them to errors.

## Unresolved risks

- Several batch commands provide no incremental progress output, so long runs can appear idle.
- Raw upstream payloads may be too large or unstable for a future direct UI contract.
- The CLI has no masking layer if an upstream response unexpectedly includes sensitive content, although secrets are not intentionally printed.
- `CORE-002` and `CORE-003` do not yet provide contextual no-subcommand help.
