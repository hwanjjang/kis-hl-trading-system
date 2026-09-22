# Initial independent core implementation review

Verdict: **CHANGES_REQUIRED**. Date: 2026-09-12.
Reviewer: `/root/review_trading_plan`; builder/coordinator: `/root`.
This is the initial bounded build-time assessment, not final candidate verification
or a PR review. Shared SDLC state and iteration receipts remain coordinator-owned.

## Consumed revisions

Hashes were captured in the same Python process that imported and exercised these
modules. Tests used fake gateways and temporary SQLite databases; no APIs or real
orders were called. Account locking was replaced with `nullcontext` only in the
test process, so these results do not validate process-level mutual exclusion.

| Input | SHA256 |
| --- | --- |
| `kis_hl/journal_sync.py` | `290d68e6a555470e3e8d1b5057f1acccc34820f4c619821fbef3e9da3c6ea979` |
| `kis_hl/journal_history.py` | `ed357d839330fb3ad252922c6b9868888c76d303442b71fac326c2e1582619c7` |
| `kis_hl/managed_execution.py` | `8ead000749586d9af9dabc662bd7f27015680a1a25f3b880f3c5b652949e3c55` |
| `tests/test_journal_sync.py` | `e3a10c894ddfb0270fb3efcc93c9134f6ebaed1f6798c00782d2fc2d1bf0d246` |
| `tests/test_journal_history.py` | `d9337a58b68a6a5a22fc5385f1ba59dbca2883c696c8ee48388c42f576ab9d75` |
| `tests/test_managed_execution.py` | `d75fb897e35e15c5774ff08ac8934c599f227e1d8c3474a5418d9fcc48bdd540` |
| `kis_hl/trailing.py` | `95b0b85022a198f87d8916f4a8a80974415b4b3871af1e6ee3886267c05529d3` |
| `kis_hl/execution_lock.py` | `9f1f14b9995e4c40b8a9951c8e8e90eb16e6314c48c6ddeac3b35965add0c177` |
| `kis_hl/trade_journal.py` | `3bfd46552484265d9d10e74c348b3f10bc356c3cf152b7f83562a067a6309971` |

## Must Fix findings

All findings below are open. Locations refer to the consumed hashes. MV3 covers
execution safety/recovery; MV4 covers actual-history journal accounting.

### C1 — HIGH / Bug: cancelled queued plans still enter

Location: `managed_execution.py:101–106,142–158`. Confidence: high. Requirement: MV3.
The QUEUED branch ignores both `cancel_entry` and `exit_requested_ms` before entry.
Reproduction: enqueue the fixture plan, call `request_exit(id, 2, cancel_only=True)`,
then `Supervisor.step(id, 10)`. Observed: `[('entry', 'SUBMITTED')]`.
An operator's cancellation therefore causes the unwanted exposure it should prevent.
Check cancellation/exit flags before preflight/transmission and terminate an unsent
plan without creating an entry attempt. Test both cancel-only and exit requests.

### C2 — HIGH / Bug: stale quotes bypass the protection deadline

Location: `managed_execution.py:159–189`. Confidence: high. Requirement: MV3.
The quote freshness return occurs before recording exposure, first-fill time,
order terminality or the unprotected-exposure deadline. Fresh account evidence of
a fill can therefore remain unhandled indefinitely because market data is stale.
Reproduction: submit entry at 10; set fixture `size=entry_filled=0.4`; make snapshot
`time_ms=0`; step at 6000 and 12000 with a 5000ms grace budget. Observed:
`DEGRADED`, `first_fill_ms=None`, attempts `['entry']`.
Reconcile account facts independently of quote freshness. Persist the fill/deadline
and perform permitted cancellation/protection/compensation or explicit intervention
when stale prices prevent an exit; never silently postpone the protection timer.

### C3 — HIGH / Bug: final permitted exit disables its own reconciliation

Location: `managed_execution.py:135,232–246`. Confidence: high. Requirement: MV3.
`len(exits) >= max_exit_attempts` moves the position to INTERVENTION even while the
last allowed exit is unresolved. `step` then permanently skips snapshots for that
position, including later fills and stop cleanup.
Reproduction: use `max_exit_attempts=1`; fill the entry, establish its stop, request
exit, and step twice while the exit remains open. Observed: INTERVENTION. Mark the
exit filled and position flat, then step again: still INTERVENTION with the attempt
SUBMITTED. Apply submission budgets only to a proposed new attempt; always reconcile
outstanding actions and flat-position cleanup, including after intervention.

### C4 — HIGH / Bug: rejected entry cancellation waits without a bound

Location: `managed_execution.py:223–234`. Confidence: high. Requirement: MV3.
Any previous cancellation prevents another attempt, including a REJECTED one.
The entry-active return precedes the exit deadline check. A rejected cancel leaves
a residual entry live and a partial position unprotected indefinitely.
Reproduction: fill 0.4, use an unavailable protective provider, make `cancel` return
`{'status':'rejected'}`, then step at 6000 and 999999. Observed: EXIT_PENDING with
entry SUBMITTED and cancel REJECTED; no retry, deadline transition or exit.
Give cancellation its own reconciled status and bounded retry/deadline policy.
Unknown cancellation must not cause competing sales, but rejection must not produce
an endless silent wait. Preserve native coverage and expose actionable intervention.

### C5 — HIGH / Security: stop readback does not prove protective semantics

Location: `managed_execution.py:198–213`. Confidence: high. Requirement: MV2/MV3.
Coverage checks only status, `kind='stop'`, size and a lower trigger bound. It does
not establish instrument, side, reduce-only, trigger comparator or post-trigger type.
Reproduction: after stop submission, modify the fake readback to `side='buy'`,
`reduce_only=False`, `trigger_type='tp'`, retaining kind/size/trigger price. Observed:
PROTECTED with covered size 1. A generic stop label must not certify protection.
Require the gateway to return a strictly validated protective contract (or check its
fields here), bind it to the expected account/instrument/order, and reject missing
or contradictory semantics. Real gateway integration must cover this boundary.

### C6 — HIGH / Bug: crash during entry cancellation loses a latched exit

Location: `managed_execution.py:195–197,221–231`. Confidence: high. Requirement: MV3.
The trigger sets `exit_requested_ms` in memory, but `_send(cancel)` persists only
the attempt. A process death after cancellation can erase the durable exit decision.
Reproduction: partial fill 0.4 with local SL, establish monitoring at price 100;
next tick is 95. In fake `cancel`, set the original order canceled then raise
`SystemExit` to simulate process death. Reload and step at rebound price 100.
Observed: persisted exit latch is None; restart returns PROTECTED with attempts
`['entry', 'cancel']`. Persist the exit latch, threshold and deadline before any
network action. Add a crash boundary regression; rebound must never erase an exit.

### C7 — MEDIUM / Bug: lexical execution IDs corrupt equal-time chronology

Location: `journal_sync.py:_fills`. Confidence: high. Requirement: MV4.
Sorting `(time_ms, execution_id)` treats a string ID as a causal sequence. Numeric
IDs '10' and '2' reverse chronological order at equal timestamps.
Reproduction: ingest BTC buy 1 with ID '2', `position_before=0`, then sell 1 with
ID '10', `position_before=1`, both at time 10, with complete history/costs.
Observed: no completed journal; an OPEN position remains despite net zero fills.
Preserve documented venue sequence or explicitly reconstruct order from supported
position continuity. Ambiguous equal-time ordering must remain pending with its
reason, rather than inventing an order from arbitrary string identity.

### C8 — MEDIUM / Bug: correction snapshots count superseded cycles

Location: `journal_sync.py:_reconcile`, stats generation before removed-cycle
supersession. Confidence: high. Requirement: MV4.
Existing effective cycles are used to calculate a new snapshot before cycles
removed by the same correction are marked SUPERSEDED.
Reproduction: import buy1/sell1/buy1/sell1 at times 10/20/30/40 with IDs a/b/c/d.
Correct b to sell0.5 and c to buy0.5. The source now defines one flat-to-flat cycle.
Observed: effective entries = 1, newest `stats_json.trade_count = 2`.
Determine the entire new effective cycle set first, then calculate snapshots against
that set and persist revision/supersession atomically. Preserve historical snapshots
but do not create a new snapshot with already-invalid performance observations.

### C9 — HIGH / Spec: returned row count cannot establish retention coverage

Location: `journal_history.py:43–55`. Confidence: high from code inspection;
not tested against the live API. Requirement: MV4.
`len(raw) < 10000` sets coverage complete if normalization succeeds. A bounded old
window can return fewer rows or none after retention eviction, including when the
latest retained fills lie outside that window. Recursive paging cannot recover
evicted executions, and an ended page is not evidence of historical completeness.
The resulting sync run advertises complete coverage without a verified retention
anchor, making missing external closed cycles invisible to later cursor logic.
Add a fake-history scenario with evicted old fills and a short/empty requested-window
response. Require coverage evidence from a verified retained boundary, previous
continuous ingestion or statement import; otherwise persist an explicit gap rather
than a successful complete interval. The existing total-count check is insufficient.

## Executed evidence

The inline Python reproductions used `tests.test_managed_execution.Gateway` and
`plan`, `Supervisor`, and `JournalLedger`, with private temporary databases. They
printed the observed states documented above. C1–C8 were reproduced; C9 is a
code-path/contract finding requiring a retention fixture regression.

The current suites were also run through `unittest` in the isolated fake-lock
process: `tests.test_journal_sync`, `tests.test_journal_history`, and
`tests.test_managed_execution`: **22 tests passed, 0 failures, 0 errors**.
Passing these tests does not cover the reproduced counterexamples.

## Limits and follow-up

No source, tests or shared SDLC state was edited; this report is the sole retained
write. No network, accounts, trading, messages, commits or further delegation.
The gateway/CLI implementation remains outside this bounded candidate assessment.
Final verification must recheck current hashes, gateway semantic contracts, actual
account-lock concurrency, multi-position iteration, KIS cancel/sell reservation,
legacy journal linkage and correction recovery with the complete candidate.
Fees and reversal allocation have baseline unit coverage, but this report is not a
claim of exhaustive accounting or live exchange verification.
