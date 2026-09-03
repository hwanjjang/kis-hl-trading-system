# Acceptance Criteria

## Scope and interpretation

These criteria specify observable current-product behavior. They do not authorize live tests, new UI, or planned strategy-daemon behavior. Unit and integration verification must stub external transports; any live verification is a separately approved operational activity.

## Global CLI contract

| ID | Screens | Given | When | Then |
| --- | --- | --- | --- | --- |
| AC-GEN-001 | All | A leaf command completes successfully | The process exits | Exit code is 0 and one valid JSON result is written to stdout. |
| AC-GEN-002 | All | A command handler raises an exception | The process handles the failure | A structured `cli_command_failed` log is emitted, JSON containing `error` is written to stderr, and exit code is 1. |
| AC-GEN-003 | CORE-001, CORE-002, CORE-003 | No executable leaf handler is selected | Parsing completes | Help is printed and exit code is 2; no external or local write occurs. |
| AC-GEN-004 | All leaf surfaces | A non-default `--db` precedes the command | A local read/write is performed | The exact supplied database path is used. |
| AC-GEN-005 | All external surfaces | An external request is active | Output and logs are produced | Configured secrets, private keys, and bearer tokens are not intentionally included. |
| AC-GEN-006 | All | A command is run on a narrow terminal | Output is produced | The same text/JSON contract is preserved; no mobile-specific UI is claimed. |

## Market, account, and symbol criteria

| ID | Screens | Given | When | Then |
| --- | --- | --- | --- | --- |
| AC-MKT-001 | MARKET-001 | Valid KIS config and a domestic symbol | `kis-price --market domestic` runs | The domestic quote route is used and JSON contains status and raw body. |
| AC-MKT-002 | MARKET-001 | Valid KIS config and an overseas symbol/exchange | `kis-price --market overseas` runs | The overseas quote route receives the selected exchange code. |
| AC-MKT-003 | MARKET-001, MARKET-002 | A KIS response is HTTP-failed or body-failed | Storage was requested | The command exits 1 and does not store the response as a successful market record. |
| AC-MKT-004 | MARKET-001, MARKET-002 | A KIS request succeeds and `--store` is set | The result is returned | `stored_id` is present and the raw payload is retrievable from `market_ticks`. |
| AC-MKT-005 | MARKET-002 | Symbol, from/to dates, period, and market code are valid | `kis-daily` runs | The overseas daily-chart route receives those values and the raw body is returned. |
| AC-MKT-006 | MARKET-003 | No symbol filter is supplied | `hl-mids` succeeds | The complete returned mids object is emitted. |
| AC-MKT-007 | MARKET-003 | Spot, perp, or trade.xyz symbols are supplied | `hl-mids` succeeds | Each requested symbol has a resolved record and a mid value or explicit null; spot order coin is resolved via spot metadata when needed. |
| AC-MKT-008 | MARKET-004 | Valid symbol, interval, and time bounds | `hl-candles` succeeds | JSON contains the upstream candle array, including an explicit empty array when applicable. |
| AC-ACC-001 | ACCOUNT-001 | A funded account address is explicit or configured | `hl-account` runs with defaults | Main perp and spot state are requested and the output names the queried address. |
| AC-ACC-002 | ACCOUNT-001 | Repeated dex values and `--no-spot` are supplied | `hl-account` runs | Spot is omitted and each named dex state is represented. |
| AC-ACC-003 | ACCOUNT-001 | No account address is available | `hl-account` runs | The command exits 1 with an address-related error and performs no signed action. |
| AC-SYM-001 | ASSET-001 | `BTCUSDC`, a BTC perpetual alias, or a trade.xyz alias is supplied | `resolve-symbol` runs | The output identifies the correct spot/perp kind, L1 coin, and dex without a network call. |
| AC-SYM-002 | ASSET-001 | An unsupported or malformed symbol is supplied | Resolution runs | The input is rejected with exit 1 rather than guessed. |

## Strategy and order safety criteria

| ID | Screens | Given | When | Then |
| --- | --- | --- | --- | --- |
| AC-STR-001 | STRATEGY-001 | At least the required closed 3-hour candles exist | Latest close is strictly above the highest configured prior high | `should_enter` is true and the evidence fields identify the threshold and latest close. |
| AC-STR-002 | STRATEGY-001 | Latest close equals or is below the breakout level | The signal is evaluated | `should_enter` is false and no order method is invoked. |
| AC-STR-003 | STRATEGY-001 | Candle history or lookback is invalid/insufficient | Evaluation runs | The command exits 1 rather than manufacturing a neutral or positive signal. |
| AC-STR-004 | STRATEGY-002 | No explicit ATR is supplied | The monitor starts | ATR(10D) is calculated from fetched BTC perpetual daily candles before streaming. |
| AC-STR-005 | STRATEGY-002 | An explicit ATR is supplied | The monitor starts | The supplied Decimal value is used and no ATR fetch is required. |
| AC-STR-006 | STRATEGY-002 | A qualifying closed 3-hour spot breakout occurs in default mode | A plan executes | Entry and stop are dry-run, default entry notional is 80 USDC, default stop distance is ATR × 2, and no signed order is sent. |
| AC-STR-007 | STRATEGY-002 | No qualifying breakout occurs before a configured stop condition | The monitor ends | `executions` is empty and final websocket status is returned. |
| AC-STR-008 | STRATEGY-002 | Execution storage is enabled | A plan emits entry and stop results | Both submissions and the protective stop are stored and returned IDs identify all three rows. |
| AC-ORD-001 | ORDER-001 | Any syntactically valid supported order omits `--live` | `trade` runs | Result has `dry_run=true`, response indicates skip/dry-run, and the exchange SDK does not send an order. |
| AC-ORD-002 | ORDER-001 | A limit order omits price | Validation runs | The command exits 1 before an external order action. |
| AC-ORD-003 | ORDER-001 | A stop-market order omits trigger price or reduce-only | Validation runs | The command exits 1 before an external order action. |
| AC-ORD-004 | ORDER-001 | A live symbol is outside the supported allowlist | `--live` is supplied | The order is rejected before credential loading or exchange action. |
| AC-ORD-005 | ORDER-001 | A live trade.xyz order uses an eligible asset but has no recent successful verification in the selected database | Submission is attempted | The order is rejected before credential use or exchange action. |
| AC-ORD-006 | ORDER-001 | A supported applicable live order lacks wallet address or private key | Submission is attempted | The order is rejected with the missing credential category and no exchange action. |
| AC-ORD-007 | ORDER-001 | A non-reduce-only live trade.xyz entry is outside its underlying regular session | No override is supplied | The order is rejected and the session cause is diagnosable. |
| AC-ORD-008 | ORDER-001 | The same outside-session entry is otherwise valid | `--allow-outside-session` is explicit | The session decision is retained in the request and the guard may proceed to submission. |
| AC-ORD-009 | ORDER-001 | A live supported order passes all applicable guards and the exchange accepts it | Submission returns | Result has `dry_run=false`, `status=submitted`, exchange response, and timestamp. |
| AC-ORD-010 | ORDER-001 | Storage is enabled | A dry-run or live submission completes | `stored_id` is present and the row contains input symbol, resolved symbol, side, type, size, price/trigger, dry-run flag, status, response, and time. |
| AC-ORD-011 | ORDER-001 | A reduce-only stop-market submission is stored | Persistence completes | `protective_order_id` is present and the protective row links to its source order submission with trigger and covered size. |
| AC-ORD-012 | ORDER-001, STRATEGY-002 | `--no-store` is set | A result completes | No local order/protective row is created, while the external-action semantics remain determined solely by `--live`. |

## Journal criteria

| ID | Screens | Given | When | Then |
| --- | --- | --- | --- | --- |
| AC-JRN-001 | JOURNAL-001 | A fully closed long/buy position omits authoritative realized PnL | It is added | Net PnL is `(exit-entry)×quantity-fees`; return percentage uses entry notional. |
| AC-JRN-002 | JOURNAL-001 | A fully closed short/sell position omits authoritative realized PnL | It is added | Net PnL is `(entry-exit)×quantity-fees`. |
| AC-JRN-003 | JOURNAL-001 | Authoritative realized PnL is supplied | It is added | That value determines outcome and return and fees are not subtracted a second time. |
| AC-JRN-004 | JOURNAL-001 | Close time precedes open time, numeric input is invalid, or quantity is invalid | Record creation runs | The command exits 1 and does not store a valid-looking record. |
| AC-JRN-005 | JOURNAL-001 | A record is added | Storage completes | One new ID is returned with derived return, outcome, elapsed 24-hour holding days, and a statistics snapshot. |
| AC-JRN-006 | JOURNAL-002 | Symbol and/or strategy filters are supplied | Statistics run | Metrics and entries use exactly the matching population and echo the filters. |
| AC-JRN-007 | JOURNAL-002 | The population contains wins and losses with unequal sizes | Statistics run | Averages and ratios use unweighted `realized_pnl_pct`, not currency PnL. |
| AC-JRN-008 | JOURNAL-002 | The population contains breakevens | Statistics run | Breakevens remain in trade count and are excluded from decisive win-rate and ratio denominators. |
| AC-JRN-009 | JOURNAL-002 | No wins, no losses, or no matching records exist | Statistics run | Metrics that require the missing side are null; infinity or invented ratios are not emitted. |
| AC-JRN-010 | JOURNAL-001, JOURNAL-002 | `adjusted_outcome` differs from calculated net-PnL outcome | Statistics run | The legacy field remains stored/readable but does not alter the nine required metrics. |

## Asset governance and market-evidence criteria

| ID | Screens | Given | When | Then |
| --- | --- | --- | --- | --- |
| AC-AST-001 | ASSET-002 | A writable fresh database | `xyz-assets seed` runs | Schema/rows are created and returned count matches the curated code seed. |
| AC-AST-002 | ASSET-003 | Seeded rows and optional filters | `xyz-assets list` runs | Count equals listed rows and filters restrict results without mutating eligibility. |
| AC-AST-003 | ASSET-004 | Default verification mode | Verification runs | Only tradable rows, optionally restricted by class, are checked against `xyz` mids and every result is persisted. |
| AC-AST-004 | ASSET-004 | `--all` is set | Verification runs | Excluded rows are also checked but their curated tradability is not changed. |
| AC-AST-005 | ASSET-005 | A previous stored/explicit universe exists | Current universe is collected | `new_symbols` and `missing_symbols` are set differences, and unmapped symbols remain separate from curated eligibility. |
| AC-AST-006 | ASSET-005 | No previous snapshot exists | First snapshot runs | The curated seed is used as the comparison baseline. |
| AC-AST-007 | ASSET-005 | `--no-store` is set | Collection succeeds | `stored=false`, `snapshot_id` is null, and observed counts/deltas are still returned. |
| AC-AST-008 | ASSET-006 | A symbol returns funding rows | Collection succeeds | Per-symbol row count, stored-row count, latest funding rate, and latest premium are reported. |
| AC-AST-009 | ASSET-006 | A symbol returns no funding rows | Collection succeeds | Status is success, row counts are zero, and latest values are null. |
| AC-AST-010 | ASSET-007 | Valid bid and ask levels exist | Spread collection succeeds | Mid, absolute spread, bps, bid/ask prices and sizes are returned and optionally stored. |
| AC-AST-011 | ASSET-007 | Bid/ask levels are missing or best ask is below best bid | Spread is calculated | That symbol fails explicitly; no fabricated zero spread is stored. |
| AC-AST-012 | ASSET-006, ASSET-007 | One symbol fails and fail-fast is false | Batch continues | Later symbols run and summary/per-symbol results expose the failure. |
| AC-AST-013 | ASSET-006, ASSET-007 | One symbol fails and fail-fast is true | Batch runs | The command exits 1 at the failure rather than returning a misleading complete summary. |

## Mapping, fallback, and history criteria

| ID | Screens | Given | When | Then |
| --- | --- | --- | --- | --- |
| AC-KIS-001 | KISMAP-001, KISMAP-002 | A fresh database is seeded | Mappings are listed | Active, excluded, and unsupported states/reasons are preserved and filters do not change them. |
| AC-KIS-002 | KISMAP-003 | No mapping exists or its status is not active | A mapped fetch is requested | The command exits 1 before a KIS request and reports the mapping cause. |
| AC-KIS-003 | KISMAP-003 | An active domestic, overseas, domestic-index, or overseas-index-time mapping exists | Fetch runs | The mapped KIS client method and configured codes are used; mapping and response are returned together. |
| AC-KIS-004 | KISMAP-004 | Active and inactive mappings are selected | Batch runs without fail-fast | Active rows are requested; inactive rows are `skipped` with reason; failures do not erase successes. |
| AC-KIS-005 | KISMAP-004 | Storage is enabled | Active quote calls succeed | Each success with a stored row has `stored_id`, and summary `stored` equals those results. |
| AC-REF-001 | REFMAP-001, REFMAP-002 | Secondary mappings are seeded | They are listed/filterable | Provider, provider symbol, asset class, status, and reason remain explicit. |
| AC-REF-002 | REFMAP-003 | Mapping is missing or inactive | Fetch is requested | The command exits 1 before provider access and identifies the mapping state. |
| AC-REF-003 | REFMAP-003 | Active mapping and valid range/interval | Fetch succeeds | Mapping, provider status/body, observation timing, and optional stored ID are returned. |
| AC-REF-004 | REFMAP-004 | A mixed batch is selected | Collection runs | Results classify success, skipped, and failed rows, and summary counts reconcile. |
| AC-HIS-001 | HISTORY-001 | Tradable assets are selected | Routes resolve | An active secondary mapping is used when present; otherwise the curated underlying symbol and exchange are used. |
| AC-HIS-002 | HISTORY-001 | Days and optional exclusive end date are valid | Collection runs | The requested date window is reported and normalized daily bars are upserted when storage is enabled. |
| AC-HIS-003 | HISTORY-001 | A selected asset is ineligible or lacks an active route | Collection runs without fail-fast | It is skipped or failed with cause rather than assigned a guessed route. |
| AC-BATCH-001 | KISMAP-004, REFMAP-004, HISTORY-001 | Per-symbol failure occurs with fail-fast false | Remaining work exists | Processing continues and final results preserve cause, action outcome, and aggregate counts. |
| AC-BATCH-002 | KISMAP-004, REFMAP-004, HISTORY-001 | `--no-store` is set | Calls succeed | Data is returned but local stored counts remain zero. |

## Documentation acceptance

| ID | Given | When | Then |
| --- | --- | --- | --- |
| AC-DOC-001 | `screen-inventory.md` and `screen-specs.md` | Screen IDs are compared | The same 29 unique IDs appear once in each file. |
| AC-DOC-002 | Every screen section in `screen-specs.md` | Required field labels are counted | Purpose, entry, role, data, actions, empty, loading, error, permissions, mobile, and completion are each present once. |
| AC-DOC-003 | The eight requested files | Paths are enumerated | All exist under `docs/product` and no production-code file is changed by this task. |
| AC-DOC-004 | A statement is not established by code, tests, or a cited reference | Product docs are reviewed | It is placed under an Assumptions or Unresolved risks section rather than described as implemented functionality. |

## Out-of-scope future acceptance

No acceptance criteria are defined for a GUI, authentication/RBAC, approvals, notifications, autonomous trade.xyz daemon, automatic fill reconciliation, tick/lot rounding, exposure/liquidation guards, or automatic funding/spread gates. Those capabilities require explicit product decisions before specification.

## Assumptions

- **A-005:** Automated verification uses fake/stub transports and local temporary databases; live correctness is not inferred from unit success.
- **A-023:** “Current behavior” includes known limitations when the tests and implementation agree, even if a safer future design is documented elsewhere.
- **A-024:** External provider success/error payloads can change, so assertions focus on routing, handling, and preserved evidence rather than undocumented vendor fields.

## Unresolved risks

- Some operational requirements in `user-flows.md` are manual and cannot be proven by the current CLI alone.
- Exchange-level price/size and reduce-only rejection behavior requires testnet or explicitly approved small live validation beyond this documentation scope.
- Documentation acceptance does not establish that all product acceptance criteria already have automated tests.
