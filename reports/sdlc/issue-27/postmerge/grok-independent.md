# Independent verification — issue 27 post-merge lifecycle

Verdict: **PASS**

This is independent verification of the frozen post-merge candidate only. It is not a pull-request review, not a merge-ready receipt, and it does not authorize merge or live trading. No product, test, documentation, skill, shared plan, or SDLC state file was changed.

## Identity

| Item | Observed |
| --- | --- |
| Reviewer | Grok 4.7. User assignment for this pass: grok-4.7 / high / auto. |
| Runtime exposure | This session `summary.json` records `current_model_id=grok-4.7` and `reasoning_effort=high`. It has no permission-mode field. Process environment exposed `GROK_AGENT=1` only. Process argv was not re-read here. Python 3.12.3 via `/tmp/hl-trailing-venv`. |
| Candidate | `86c59c56ab890f884849ec863ccb1de7cd4481ac64aa31ce09c7e8d7779f305a` |
| Base | `4b558e0da2e55c6a9321fc81ce0d5b052054e262` (`HEAD`, branch `fix/issue-27-add-lifecycle`) |
| Candidate shape | Content digest in `reports/sdlc/issue-27/postmerge/candidate.json`, not a git commit. Working tree matches all 33 declared file digests. Both deleted browser sidecars are absent. |
| Aggregate preimage | Not reproduced. Tried canonical JSON of the file map, base+files+deleted, path/digest lines, and `changes.diff`. None equaled the declared digest. Identity used here is the per-file match. |
| Out of candidate | Dirty `reports/sdlc/issue-27/artifacts.json` is outside the frozen file list. It was not used as behavior evidence and was not modified. |

`git diff --check` against the tracked post-merge delta exited 0 with empty output (`grok-independent-diff-check.log`).

## Scope challenged

Both corrections were checked against `specs/issue-27.md` ("Post-merge lifecycle corrections"), `docs/trading-operations.md` (per-target `cancel_started_ms` and terminal retirement), and `docs/architecture/add-termination.workflow.json`. Generated HTML was not re-rendered or opened. Existing diagram receipts were not re-executed.

Code under test:

- `kis_hl/managed_execution.py`: `retire_unsent_adds` (about line 252), terminal `save` (about 348), finished-owner repair in `Supervisor.step` (about 468), per-attempt `cancel_started_ms` (about 933–970). The diff replaces the owner-scoped `row["cancel_started_ms"] = row.get("cancel_started_ms") or now` write. Deadline comparison stays `>` and the retry comparison stays `len(prior) >= max_exit_attempts`.
- `kis_hl/operations_cli.py`: `order status` (about 551) and `supervisor status` (about 602) only read. This file is unchanged versus the base; the candidate still hashes it.

Admission note: an owner forced to `ENTERING` is rejected by add execution and creates no tranche or gateway send. Simultaneous entry+add was not treated as a supported path. No synthetic multi-entry seed was scored as a product defect.

## Commands and results

All commands used `/tmp/hl-trailing-venv/bin/python` from the repository root. Fixtures and probes used temporary SQLite and the existing stub gateway. Sockets were forbidden on the smoke and status probes. `.env` was not read (`load_env_file` patched on CLI probes). No live exchange or account call was made. Stdout lines that mention Hyperliquid orders come from existing offline unit tests.

| Command | Exit | Result |
| --- | --- | --- |
| `python -m unittest tests.test_add_lifecycle tests.test_conditional_add tests.test_strategy_tools tests.test_strategy_signals tests.test_managed_execution tests.test_managed_gateways tests.test_manual_adoption tests.test_native_trailing tests.test_hyperliquid_client tests.test_operations_cli tests.test_risk tests.test_execution_lock tests.test_websocket_streams -q` | 0 | Ran 221 tests in 32.829s, OK. Log: `grok-independent-tests.log`. |
| `python -m unittest tests.test_add_lifecycle -q` | 0 | Ran 11 tests in 5.591s, OK. Log: `grok-independent-add-lifecycle.log`. |
| `python scripts/smoke_conditional_add.py` | 0 | Passed. Stub gateway, temporary SQLite reopened by each CLI call, sockets forbidden. Historical-entry cancel, partial fill under pending cancel, and legacy queued-add repair passed. Log: `grok-independent-smoke.log`. |
| `PYTHONPATH=. python reports/sdlc/issue-27/postmerge/grok-independent-probes.py` | 0 | 10 probes, 0 failed. Log: `grok-independent-probes.log`. |
| `git diff --check` | 0 | Empty. |

The 221-test run includes the lifecycle module, so unknown-target intervention, unknown-cancel non-retry, legacy interval table, partial-fill SL extension, and terminal retirement are independently executed results, not the builder's log.

## Probe dispositions

No mandatory finding. Design-review probes F1–F8 were exercised as follows.

| Probe | Result | Evidence |
| --- | --- | --- |
| Deadline cap without consuming the retry cap | Pass | One non-rejected cancel. At `exit_deadline_ms` (60000) state stayed `ENTERING` and no second cancel was sent. One millisecond later state became `INTERVENTION` and the cancel count stayed 1 through a later tick. The exclusive `>` boundary is the pre-change operator, now applied to the target attempt clock. |
| Retry cap before the deadline | Pass | Three rejected cancels in 3ms (`max_exit_attempts=3`) then `INTERVENTION`. Elapsed time stayed far below 60000. No fourth cancel. |
| Crash after the clock commit and before the cancel row | Pass | `SystemExit` inside cancel `_send`. Reopen showed `cancel_started_ms` equal to expiry and zero cancel rows. The next tick sent exactly one `SUBMITTED` cancel and did not move the clock. |
| Partial fill during pending cancel, crash during incremental stop | Pass | Covered size became `1.2`, cancel count stayed 1, state stayed non-`INTERVENTION` (`ENTERING` because the stub acknowledgement is not terminal). |
| Old owner clock versus a later add | Pass | Stale owner clock `opened+1001` was before add creation. The add clock was its own expiry, with one cancel and no `INTERVENTION`. |
| Owner timestamp inside the matching-cancel interval | Conforms, not a defect | A foreign timestamp strictly inside `[attempt.created_ms, earliest matching cancel]` was stored as that attempt's start. The amended spec and operations doc require this attribution. Supported history places the previous cycle's clock before the new add, which the poison probe covers. It does not widen a new add's budget. |
| Unknown target and unknown cancel | Pass via executed tests | `tests.test_add_lifecycle` (inside the 221 and the separate 11) covers missing `order_id` (clock set, no cancel, `INTERVENTION`, no resend) and `KeyboardInterrupt` during cancel (durable clock, one `UNKNOWN`, no retry, later deadline intervention). |
| Cleanup transaction rollback | Pass | Two legacy unsent `QUEUED` tranches plus one `QUEUED` tranche with a durable `UNKNOWN` attempt and signature. The second retirement encode raised inside `retire_unsent_adds`. Both unsent rows stayed `QUEUED` with no `retired_ms`. The retry then canceled only those two. The signed tranche stayed `QUEUED` and the attempt stayed `UNKNOWN` with its signature. |
| Status read purity and repair | Pass | Legacy `CLOSED` plus unsent `QUEUED`, written without `save()`. `order status` and `supervisor status` exited 0, left every SQLite table snapshot unchanged, and still reported `QUEUED`. The next supervisor step called retirement once and stored `CANCELED` with plan and sizing preserved. |
| All finished states | Pass | For `CLOSED`, `REJECTED`, and `PREVIEWED`, a raw finished owner kept an `UNKNOWN` tranche and its signature across a repair step, then a replacement unsent `QUEUED` tranche was retired at the step timestamp. |
| Entering owner plus add | Rejected admission | `signals.execute` raised, sent nothing, and left no tranche. |

Owner `save` and `retire_unsent_adds` are separate commits. That matches the stated repair rule: a crash between them leaves the finished owner and the unsent tranche for the next supervisor tick. The cleanup check and tranche updates themselves share one `BEGIN IMMEDIATE` transaction, and the injected failure rolled that transaction back. This is not filed as a defect.

## Findings

None. No BLOCKER, HIGH, MEDIUM, LOW, or NIT is filed. There is no unresolved mandatory finding and no missing mandatory verification inside the authorized offline scope.

## Limitations

- Live exchange behavior, real accounts, credentials, and broker acknowledgement races were not exercised.
- Diagram HTML, browser viewports, and perceptual images were not re-run. Alignment was checked from the workflow source and the code/probes above.
- The declared 64-character candidate digest's canonical preimage is undocumented here; file-level identity was verified instead.
- Permission mode is not in this session `summary.json`. It was not re-confirmed from process argv.
- A legacy owner timestamp with no matching cancel row restarts at the current tick. That is the specified rule, because the old owner field is not attributable without matching cancel history. The new code writes the attempt clock before cancel submission, so a crash on the current path does not depend on the owner field.
- `Supervisor.step` calls finished-owner repair outside its reconciliation `except` clause. An unexpected retirement exception aborts that call instead of rewriting the finished owner. Not observed on the supported paths above.
- This pass does not certify CI, a published PR head, or review eligibility for a later exact-head pull-request review.

## Evidence files

- `reports/sdlc/issue-27/postmerge/grok-independent.md`
- `reports/sdlc/issue-27/postmerge/grok-independent-probes.py`
- `reports/sdlc/issue-27/postmerge/grok-independent-probes.log`
- `reports/sdlc/issue-27/postmerge/grok-independent-tests.log`
- `reports/sdlc/issue-27/postmerge/grok-independent-add-lifecycle.log`
- `reports/sdlc/issue-27/postmerge/grok-independent-smoke.log`
- `reports/sdlc/issue-27/postmerge/grok-independent-diff-check.log`
