# Independent foundation review

Reviewer: `/root/verify_data_foundation` (independent agent). Date: 2026-09-13.

Disposition: **changes required on the reviewed implementation**. This report records the initial findings; it is not approval of the eventual complete candidate. The implementation owner acknowledged the first three findings and is preparing corrections. A separate final-candidate verification must validate those corrections and the combined implementation.

## Scope and method

Read `AGENTS.md`, task-observer, karpathy-guidelines, trade-journal and both journal metric/record references. Reviewed the accepted unified-data spec and implementation plan against `data_store.py`, `data_migrations.py`, `data_import.py`, `data_quality.py`, `data_maintenance.py`, `journal_exports.py`, and `tests/test_unified_data.py`. Read `data_ingestion.py` and `analysis_store.py` to trace callers and consumers.

Ran `python3 -m unittest tests.test_unified_data -q`: **7 tests passed**. Independently exercised adversarial accounting, export, import and derived-lineage cases using synthetic values and `TemporaryDirectory` databases. No private datasets, credentials, network, signed orders, product edits or commits were used. The tests passed before the failures below were reproduced, demonstrating coverage gaps rather than preexisting failing tests.

## F1 — P1: partial exit followed by an add overstates realized profit

Location: `kis_hl/journal_exports.py`, `account_cycles`, locally calculated closing cost basis.

The exit basis uses cumulative `entry_notional / entry_quantity`, including inventory already sold. After adding to a partially reduced position, the average basis no longer represents remaining inventory.

Synthetic sequence, zero costs, no authoritative source `gross_pnl`:

| Operation | Quantity | Price | Cash flow |
| --- | ---: | ---: | ---: |
| Buy | 10 | 100 | -1000 |
| Sell | 5 | 200 | +1000 |
| Buy | 5 | 300 | -1500 |
| Sell | 10 | 200 | +2000 |

Cash-conserved gross profit is **500**. Calling `account_cycles` with distinct timestamps and `kis:SYNTH` produced **833.3333333333333333333333330**, with no quality issues. This affects KIS/portable statements whose gross profit is calculated locally and can certify incorrect net profit and return statistics.

Required correction: track remaining inventory cost separately from the cumulative entry-notional return denominator. Preserve reported native closed profit where authoritative. Test partial reduce/add/final close, short symmetry, reversal, and open realized-profit conservation.

## F2 — P1: report export can destroy the canonical database

Location: `kis_hl/journal_exports.py`, `export_report`, output path validation before `os.replace`.

Synthetic reproduction:

```python
store = DataStore(temp_path / 'canonical.sqlite')
run_id = store.pin('journal', {}, [], {'sample': 'report'})
export_report(store, run_id, store.path)
```

Observed: `DatabaseError: file is not a database` is raised after replacement. The database header changes from `SQLite format 3` to the report JSON `{"sample":"report"}`. Subsequent `store.status()` also fails. The exception does not preserve the database because replacement already occurred.

Required correction: reject the canonical database and its live SQLite sidecars as export destinations before any directory/file or report-status mutation. Resolve aliases/symlinks as applicable. Add a regression confirming the sentinel state and database bytes remain intact after rejection.

## F3 — P2: import preview misses invalid rows and apply leaves unrecorded partial progress

Location: `kis_hl/data_import.py`, `import_manifest` preview and apply loops; `data_ingestion.py`, row-by-row commits.

Synthetic manifest contains two `hl_fills` rows in one digest-valid raw file: the first is valid, and the second has `feeToken='INVALID'`. Preview reports one raw file and no problem because it checks file/digest/container shape but does not invoke the selected parser.

Observed apply result:

```text
preview: {'raw_files': 1, 'baseline_files': 0, 'applied': False, 'fact_ids': []}
apply error: Unsupported fill side or unverified collateral
effective fact count: 1
collection_runs count: 0
import_manifests count: 0
```

The first economic fact is committed despite a preview that failed to disclose the invalid source; neither manifest nor collection attempt records the incomplete import. This violates the intended reviewable preview and traceable partial-attempt contract. Keeping rejected raw evidence is appropriate and should remain possible.

Required correction: prevalidate parser rows and declared conflicts without economic mutation during preview, then ensure apply is atomic at its documented boundary or records durable failed/partial progress with resumable identity. Test invalid later rows and conflicts against existing revisions, not just digest mismatches.

## F4 — P2: upstream corrections do not mark derived analysis stale

Location: `kis_hl/data_store.py`, `status()['stale_runs']`.

The stale query considers only a direct `newer.supersedes = analysis_inputs.fact_id` relationship. Derived market facts carry their daily inputs in payload `input_ids`, but that dependency is ignored by invalidation.

Synthetic reproduction:

1. Insert daily fact ID 1 with close 10.
2. Insert weekly fact ID 2 with `input_ids=[1]`.
3. Pin analysis run ID 1 using weekly fact ID 2.
4. Explicitly correct daily fact ID 1 to a new revision with close 11.

Observed `stale_runs=[]`, although the analysis depends transitively on superseded daily data. Old immutable output remains reproducible, but the promised stale indicator is false. The retention preview already follows these same transitive input IDs.

Required correction: traverse derived dependencies for stale detection and validate their existence/knowledge timing at the appropriate fact/pin boundary. Test multi-level dependencies and ensure unrelated corrections do not stale the run.

## Positive evidence and limits

The reviewed migration uses a checksum ledger and a transaction, raw payloads are content addressed and compressed, source observations survive deduplication, and explicit corrections retain revisions. The focused tests establish direct as-of revision selection, repeated source import deduplication, basic funding-grain conflict detection, and backup/isolated-restore preservation of a synthetic operational sentinel.

This review does not certify live provider history, production migration, measured concurrent supervisor latency, market calendars, scheduler ownership, or the final combined code. Those require the complete-candidate tests and operational evidence owned by the main implementation task.
