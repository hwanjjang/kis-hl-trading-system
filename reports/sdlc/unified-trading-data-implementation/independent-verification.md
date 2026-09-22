# Independent implementation verification

**Verdict: PASS for the local implementation candidate identified below.** F1–F7 are resolved; no unresolved Must Fix remains in this review. The native weekly-gap anchor and incremental minute-polling corrections have been independently verified. This is independent software verification, not authorization for orders, a claim of complete provider history, or certification of private-account reconciliation.

Builder context: `/root`. Independent reviewer context: `/root/verify_data_foundation`. Date: 2026-09-13. Endpoint: local; no commit, PR, provider review or merge performed.

## Candidate and evidence

The exact base HEAD and SHA-256 hashes of 25 reviewed source/test/documentation/skill-reference files are recorded in [independent-candidate.json](independent-candidate.json). This includes all new `kis_hl/data_*.py`, market series/ingestion, journal export, analysis, modified CLI/KIS/Hyperliquid clients/routes, the unified-data tests and implemented operations documentation. The candidate is local uncommitted content after the incremental minute-polling correction; a later relevant edit invalidates the matching portion of this assessment.

Upstream contracts: [spec](../../../specs/unified-trading-data.md), [plan](../../../plans/unified-trading-data.md), [implementation test plan](test-plan.md). The broader design deliberately includes future logical families; the implementation's narrower physical schema and unavailable capabilities are disclosed in [operations documentation](../../../docs/unified-data-operations.md).

| Actual verification | Result | Evidence |
| --- | --- | --- |
| `python3 -m unittest tests.test_unified_data tests.test_journal_history tests.test_journal_sync tests.test_trade_journal tests.test_kis_client tests.test_cli -q` | PASS, 82 tests on the initial complete candidate | `independent-tests.log` |
| `python3 -m unittest discover -s tests -t . -q` before final input corrections | PASS, 289 tests | `independent-full-tests.log` |
| `python3 -m unittest tests.test_unified_data -q` after final corrections | PASS, 35 tests | `independent-final-targeted.log` |
| `python3 -m unittest discover -s tests -t . -q` after input corrections, before native-anchor correction | PASS, 295 tests in 17.500 seconds | `independent-final-full-tests.log` |
| `python3 -m unittest discover -s tests -t . -q` after native-anchor correction | PASS, 302 tests in 22.981 seconds | `independent-native-anchor-full-tests.log` |
| `python3 -m unittest tests.test_unified_data -q` after incremental polling correction | PASS, 48 tests | `independent-incremental-targeted.log` |
| `python3 -m unittest discover -s tests -t . -q` on the final hashed source candidate | PASS, 308 tests in 24.565 seconds | `independent-incremental-full-tests.log` |
| Independent adversarial import and financial-input probes | PASS | [independent-adversarial.json](independent-adversarial.json) |
| Independent long/short cash-conservation probes | PASS, finalized net profit 496 / -504 respectively, including four fees | Procedure below |
| Independent DST and explicit-session calendar probes | PASS, 167/169-hour weeks; unknown volume preserved | Procedure below |
| Independent non-Monday native-week coverage probes | PASS, actual missing Thursday interval only; unknown empty anchor; inconsistent anchors rejected | [independent-native-anchor.json](independent-native-anchor.json) |
| Independent incremental minute-window probes | PASS, first/subsequent windows, failed retry cursor, Korean UTC rollover and unchanged bulk defaults | [independent-incremental-probes.json](independent-incremental-probes.json) |
| Review of builder real-process smoke and load evidence | Passed evidence examined, with stated limits retained | `smoke.log`, `green.log` |
| `git diff --check -- kis_hl tests` | PASS | Command exit 0 |

All independent executions used repository tests or synthetic temporary directories. No credentials, private data, network inquiries, exchange orders or product/test edits were used. The small adversarial probes exercised real SQLite and production Python functions; transports in repository tests are synthetic/stubbed.

The builder smoke uses real CLI subprocesses and a temporary WAL database for import preview, repeated import, journal/export, analysis correction invalidation, backup/restore and retention preview. Its 200 market writes plus 100 representative operational writes yielded approximately 6.60 ms added p95 write latency. This supports that declared synthetic workload only; it is explicitly not a live supervisor benchmark. The independent reviewer inspected this evidence rather than relabeling a unit rerun as a functional smoke.

## Finding dispositions

The initial discovery and reproductions are preserved in [independent-foundation.md](independent-foundation.md). Follow-up findings arose during this iteration and were corrected before final assessment.

| ID / severity | Category / location | Finding and impact | Verification / evidence | Related contract | Confidence / disposition |
| --- | --- | --- | --- | --- | --- |
| F1 / HIGH | Accounting; `journal_exports.account_cycles` | Cumulative entry basis reused sold inventory after a partial reduction and subsequent add, overstating realized profit | Remaining inventory basis is now tracked separately. Regression passes; independent long/short sequences conserve cash and all fees | AC3; flat-to-flat and cost conservation | High; **resolved by reviewer** |
| F2 / HIGH | Data safety; `journal_exports.export_report` | Exporting to the active DB replaced it before failing | Canonical DB/sidecars and non-report extensions are rejected before mutation; existing paths are rejected. Regression confirms store remains usable | AC5; preserve operational state | High; **resolved by reviewer** |
| F3 / MEDIUM, Must Fix | Import/lineage; `data_import.import_manifest` | Parser preview originally accepted invalid rows, then apply partially committed without a failed receipt. Follow-up found invalid coverage outside preflight and failure handling | Parser rows and existing/intra-manifest conflicts are checked first. Coverage scope/range/status/types are validated before mutation. Independent injected coverage-write failure yields a failed receipt with persisted fact identity; replay deduplicates | AC2/AC5; reviewable preview and traceable retries | High; **resolved by reviewer** |
| F4 / MEDIUM, Must Fix | Lineage; `DataStore.pin/status` | Corrected daily input did not mark analysis pinned through a weekly derivative stale | Recursive pin expansion and transitive stale propagation inspected; dedicated regression passes | AC2/AC4; correction invalidation and reproducibility | High; **resolved by reviewer** |
| F5 / MEDIUM, Must Fix | Financial validation; `data_ingestion.statement` | Optional financially consumed fields accepted `NaN`/`Infinity`, allowing invalid arithmetic or report failure after import | `gross_pnl`, `position_before`, `settlement`, `day_end_quantity` now use finite decimal validation. Regression plus independent NaN/Infinity/float/bool probes pass | AC2/AC3; exact finite monetary values | High; **resolved by reviewer** |
| F6 / MEDIUM, Must Fix | Market coverage; `market_ingestion.backfill` | Builder's live read-only probe discovered Thursday-anchored HL native weeks; Monday gap enumeration incorrectly marked returned weeks missing | Native durations/alignment now validated; gap enumeration follows the observed native anchor. Empty responses remain unknown. Independent three-week Thursday fixture reports exactly the one missing week and preserves source intervals; mixed anchors rejected | AC4; provider-native intervals and truthful coverage | High for local correction; live discovery attributed to builder; **resolved by reviewer** |
| F7 / MEDIUM, Must Fix | Polling load; `data_jobs`, `data_cli.execute_job`, `market_ingestion.backfill` | Builder's operational check found minute jobs repeatedly fetching a 14-day request, potentially normalizing thousands of retained rows each minute | First run now requests 30 minutes; subsequent requests begin five minutes before the last successful collection. Independent failure/retry and Korean-date rollover checks pass; explicit history defaults remain unchanged | AC4/AC5; bounded periodic collection and failure recovery | High for local correction; operational discovery attributed to builder; **resolved by reviewer** |

F3's residual reproduction was a digest-valid one-fill manifest plus `coverage={start_ms:20,end_ms:10,status:complete}`. It initially passed preview, persisted a fill, and left a `running` receipt. The final implementation rejects both preview and apply before creating facts/runs. With valid coverage and an injected runtime failure in `store.coverage`, committed facts remain recoverable, the run becomes `failed`, and replay creates no duplicate effective fill. Partial commits are now explicit documented behavior, not incorrectly advertised atomicity.

F5's reproduction supplied valid base statement fields plus `gross_pnl='NaN'` or `position_before='Infinity'`. The final adapter rejects these before canonical economic storage. Independent checks also cover float/bool inputs for all four optional fields.

## Acceptance assessment

| Requirement | Independent assessment |
| --- | --- |
| AC1: local canonical store and preserved operational architecture | Additive transaction/checksum migration, common DB path, catalog seeding, WAL/FULL/FK connections inspected. Backup test preserves an operational sentinel. Legacy readers remain explicit and unchanged rather than silently joining duplicate ledgers. |
| AC2: evidence, identity, revisions and lineage | Content-addressed raw bytes, separate observations, explicit corrections, as-of revision selection, conflict-aware import, transitive pins and stale runs covered. Failed import progress is traceable. |
| AC3: accounting and journal eligibility | Fee/funding signs, component inclusion, mixed-grain funding quarantine, account/currency selection and finalized-only statistics inspected. Remaining-basis regression and independent long/short conservation pass. KIS DAY timestamps remain DAY; unique cost-basis/inventory sequencing never uses order time as exact execution time. |
| AC4: market storage and weekly history | Configurable ten-calendar-year target, native weekly period parameters, advancing KIS date cursor, explicit variants, incomplete-bar exclusion, partial provider coverage and sampled snapshots inspected. Missing history is disclosed rather than synthesized. DST/session probes pass. |
| AC5: safe import, backup, export, retention and operations | Import preview/apply, new-path report guards, online backup/isolated restore, idempotent retry, preview-only retention, serialized scheduler attempts and separate success clocks covered. Synthetic load evidence remains bounded to its measured workload. |
| AC6: real CLI path and documented operations | CLI registration and targeted tests pass; builder real-process smoke inspected. Operations documentation explains manifests, explicit account selection, running-process requirement, provider limits, partial imports and repair-forward rollout. |

Additional independent accounting procedure: execute buy 10 at 100, sell 5 at 200, buy 5 at 300, sell 10 at 200 with one unit of cost per fill. Gross cash-conserved profit is 500; finalized net is 496. Reverse every side for a short cycle: gross is -500 and finalized net is -504. Both results passed using canonical ingestion and journal generation with synthetic complete coverage.

Additional calendar procedure: `bounds` for the weeks beginning 2024-03-04 and 2024-10-28 in `America/New_York` yields 167 and 169 elapsed hours respectively. `derive_weekly` uses exactly the supplied session set, preserves missing volume as null, and does not replace the session calendar with weekdays. These tests validate local interval logic; they do not independently certify a broker's native weekly labeling or historical listing coverage.

Native-anchor procedure: provide synthetic native weekly bars starting on 2024-01-04 and 2024-01-18 UTC for a three-week request. The only missing interval is 2024-01-11 through 2024-01-18, and persisted event intervals remain unchanged. An empty response records `native_week_anchor_status=unknown`; inconsistent returned weekly anchors raise an error with failed coverage. Duration regressions reject a one-day interval mislabeled weekly. The implementation derives alignment from actual returned timestamps, rather than treating the builder's date-specific Thursday observation as a universal hardcoded guarantee.

Incremental-polling procedure: fix the executor clock and observe that the first minute request begins 1,800,000 ms earlier, while a subsequent request begins 300,000 ms before `_last_success_ms`. Execute three real SQLite scheduler runs with a synthetic middle-run failure; the third executor receives the first run's successful cursor, not the failed attempt time. Fix current time at 2024-01-01 16:00 UTC and exercise the KIS minute collector with a stubbed empty response: its default end is the end of January 2 in Korea, later than the incremental start. Without `start_ms`, the previous 30-calendar-day history default remains intact. These checks exercise source bounds and retry semantics without external access; they do not claim a new production load benchmark.

## Limits and handoff

Private-account import totals and any live read-only probes are owned by the builder's separate operational evidence and were deliberately not accessed here. No claim of ten years of available history, complete funding retention, all overseas minute routes, recurring host-service deployment, capital returns, dividends/transfers/corporate-action accounting, or full tick/L2 capture follows from this PASS. The implementation documents those boundaries and preserves partial/unknown statuses. Real operational rollout must retain verified backups and reconcile private quantities, fees/funding and currencies before claiming successful migration.

No independent-verification Must Fix remains. Reuse this report only for the content hashes recorded in the candidate manifest, with renewed checks for relevant subsequent changes.
