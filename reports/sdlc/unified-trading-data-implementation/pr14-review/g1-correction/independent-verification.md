# Independent G1 acceptance verification

Verdict: **PASS for the bounded G1 correction acceptance scope**. No blocking findings. This is independent-verification iteration 6, with four future attempts remaining as supplied by the parent. No shared stage state or counters were changed. This is not a formal PR-review PASS, broad-design completion, or merge-readiness declaration.

Verifier: `/root/g1_verifier`, fresh non-builder agent. Date: 2026-09-20. Builder: parent `/root`.

## Actual inputs and candidate identity

Read AGENTS.md, CLAUDE.md ownership rules, task-observer, karpathy-guidelines, trade-journal and its statistics/record-contract references. Read intent/unified-trading-data.md, plans/unified-trading-data.md, specs/unified-trading-data.md including its final G1 amendment, docs/unified-data-operations.md and the implementation acceptance ledger. Examined candidate.json, changes.diff, test-plan.md, build.md, self-verification.md and test-results.json in this directory. Independently inspected relevant ingestion, reconciliation, journal, CLI, storage, backup/restore, lock and existing route-selection source, plus the new regression tests and CLI smoke script.

Base: `294e51716d4a85ead1b5cf96d013ed00c09a7a35`; `git rev-parse HEAD` matched at verification start.

Candidate: `sha256:525b3160b420d04400471954e4a0d958263ec5aa78f48cc73c2a295bce75e44c`.

All 11 files in candidate.json were independently SHA-256 checked against their live bytes, at the start and after probes. The aggregate was reproduced as SHA-256 of `json.dumps(actual_file_hash_mapping, sort_keys=True).encode()`. It exactly matches the declared candidate. The recorded patch SHA-256 is `67a4fe967be7efdda8577baf3441b56044089b29a77cf7f5a3ed79bcef655f87`. `git apply --reverse --check reports/sdlc/unified-trading-data-implementation/pr14-review/g1-correction/changes.diff` exited 0, confirming the patch corresponds to the current candidate content. No patch was applied.

## Commands and observed results

1. `PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 python3 -m unittest tests.test_statement_cost_quality tests.test_review_corrections tests.test_canonical_inventory -q`: exit 0; 51 tests passed in 4.650 seconds.
2. `PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 python3 scripts/smoke_statement_costs.py`: exit 0; 15 actual CLI subprocesses passed. The script confirmed pending mixed-null costs, explicit correction to net PnL -1, independent reconciliation, immutable old exports, missing-source backup rejection, valid online backup and isolated restore, and cleanup.
3. Independent probe executed from a fresh `TemporaryDirectory(prefix='g1-independent-')`, with the current checkout on PYTHONPATH, bytecode writes disabled, dotenv disabled and only PATH/PYTHONPATH/environment guard variables supplied. Probe subprocess exit 0; **19 scenario checks passed**. Source and full sanitized output are [independent-g1-probe-v2-source.txt](independent-g1-probe-v2-source.txt) and [independent-g1-probe-v2-results.json](independent-g1-probe-v2-results.json). To reproduce, copy that source into a fresh temporary directory and execute `python3 /temporary-directory/probe.py /temporary-directory` with the checkout on PYTHONPATH. The outer runner verified deletion of the temporary directory after completion.
4. Candidate file and aggregate hashes were rechecked after probes: exact match.

The full suite was not independently rerun; the builder's recorded 360-test result was read as supporting evidence, and this verifier reran the bounded relevant population plus independent runtime challenges.

Verifier setup errors are not concealed or counted as product failures: the first unittest selection additionally named four nonexistent modules (`test_data_ingestion`, `test_data_reconciliation`, `test_journal_exports`, `test_data_maintenance`), so it exited 1 with four import errors; its 51 real tests passed. The corrected selection above is the acceptance run. The first custom probe used `sim` for a Hyperliquid synthetic account and stopped at environment validation. The corrected probe uses `testnet`; a nonexistent raw-observation table reference was also corrected to `source_observations` before rerun. Original probe source/output are retained separately as independent-g1-probe-source.txt and independent-g1-probe-results.json. No product code was changed to accommodate either fixture error.

## Acceptance evidence and findings

| Boundary | Independent evidence | Finding |
| --- | --- | --- |
| Mixed null fees cannot choose favorable returns | Ten additional buy/sell scenarios cover zero, positive/negative totals, negative known components and large exact decimals, each with settlement agreeing with the reported total. All retain the unknown component, mark the cycle PENDING, null net PnL/return and account net total, and exclude the cycle from confirmed statistics. `data_ingestion.py:68`, `journal_exports.py:130,190,201`. | No defect found. |
| Legitimate rebates and allocation | An unresolved fee on a four-unit reversal marks both resulting closed cycles pending, conserves total fees of 4 and known components of 5. Explicitly supplying rebate -1 resolves both cycles, with combined net PnL 36 and rebate allocation totaling -1. Existing tests cover equal known subtotal, absent detail and fully known signed rebates. | No defect found. |
| Partial exits and currency isolation | Independent partial exit/add cycle remains pending with total fee 5. In the reversal account, USD stays unresolved while the healthy EUR cycle retains net PnL 8 and one confirmed trade. | No defect found. |
| Preexisting facts and frozen reports | Loaded the baseline journal module from `git show BASE:kis_hl/journal_exports.py` into the temporary directory. It actually generated a FINALIZED +8 report from mixed-null facts. The candidate generated a PENDING/null report from the same facts; re-export of the baseline report was byte-identical. Fact revision and source-observation rows remained unchanged. | No defect found. |
| Independent reconciliation cannot certify either bad evidence population | Independently varied whether mixed-null fees exist only in the supplied statement or only in stored facts, keeping matching economic signatures. Both preview and apply reject with unresolved-cost errors. Entire logical SQL dumps before/after are identical, including no anchor/coverage/evidence mutation. Checks precede writes at `data_reconciliation.py:57` versus `:82`. | No defect found. |
| Missing/uninitialized backup source | Independent missing, zero-byte and unrelated-table sources all reject; source bytes/existence unchanged, destination parent absent and no source WAL/SHM created. CLI uses readonly DataStore at `data_cli.py:47`; initialization check is `data_store.py:59`. Valid backup/restore confirmed by the 15-process CLI smoke. | No defect found. |
| Operation documentation | Nonblocking runner rejection matches account_lock's nonblocking thread lock and LOCK_NB. KIS statement-only live restriction matches existing statement route `sim=None` and client's explicit rejection of unverified paper routes. Intent/spec/plan status now point to partial implemented/outstanding acceptance. | No defect found. |

Severity assessment: no critical, high, medium or low product findings within this bounded correction scope. Fixture/setup errors above concern verifier commands only. The reported fee and component amounts remain separately visible; this verification does not assert that unresolved provisional intermediate amounts are final returns.

## Limits and isolation

No vendor requests, live collection, orders, real account data, `.env` reads, publication, commits, pushes or delegation were performed. No product, test, documentation, index or shared-state edits were made by this verifier. Only this distinct report and uniquely named sanitized probe evidence were written in the authorized correction directory; generated executable probes and databases ran in temporary directories and were removed.

Existing broader-design gaps and deferred review suggestions were not re-reviewed. Runtime provider behavior and active account migration remain unverified. The task-observer skill was applied as an observation discipline; no new reusable observation arose, and the bounded report-only write restriction was preserved.
