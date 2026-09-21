# Second bounded independent core review

Date: 2026-09-12. Reviewer: `/root/review_trading_plan`.
Builder/coordinator: `/root`. Verdict: **CHANGES_REQUIRED** for the final frozen
candidate below. One reproduced HIGH Must Fix remains. This is a build-time
independent assessment, not final candidate verification or a PR review.

## Candidate identity and moving inputs

Source files changed during the review, as the coordinator disclosed. To avoid
testing one revision while hashing another, the final verification process read
the following files into memory, compiled imports directly from those frozen bytes
with an import loader, and calculated the hashes from the same byte strings.
No frozen-source files were written to the workspace. The end-of-process check
found **no moving inputs during that final run**.

| Actual consumed input | SHA256 |
| --- | --- |
| `kis_hl/managed_execution.py` | `d20a23d96e68a741be6d0d2672482916d40c39e53e7710606779838a2ef54a70` |
| `kis_hl/journal_sync.py` | `9e168e3b6b8078f12c784b9ac7257753cd47c70408360b25985a54e95e49bc28` |
| `kis_hl/journal_history.py` | `63dbfe293d6600f9b70519aaa272bf9cdd9b6caa43a6c81f4ebd2ae6ffe28d42` |
| `kis_hl/managed_gateways.py` | `563220eaa21b21796799718df857b5430b17cb7b17a76643631e920ed3d6259e` |
| `kis_hl/strategy_signals.py` | `4917c022517b4ddcd2e842e436bba5b1da8bd41b14dd2019b8306a766756bddd` |
| `kis_hl/instruments.py` | `8be436455726599a4b20fed49a18760989d854d2c78f787ce5c727cf75ad2343` |
| `kis_hl/kis/routes.py` | `9e327ad4d226981bf6ba685acadeb2e9d2c47c2a564402e7f4acc120f137f5d4` |
| `tests/test_managed_execution.py` | `cd384e694be4c23149b83a702182bafa0f19de207e5c01501c8f8284551a4097` |
| `tests/test_journal_sync.py` | `0657bb4da4a213a3c0be1de5014ea893d85ab60f6088f33d7f20edbeddc36f51` |
| `tests/test_journal_history.py` | `664488e9c3b306a7ca8ba61db7bcddc2cb0d1308a52edf5c769e97b1806ac285` |
| `tests/test_managed_gateways.py` | `021d5f5d3c66c8192917c4acc9f37cd42784731b3bcfb1846436b2d004ecdd3c` |
| `tests/test_strategy_signals.py` | `47189985142ab75594efd451c4d964926132da5000ad949b3e0e414f990fa25b` |

Earlier reads consumed older managed-execution revisions beginning `f17a7be6`,
`8c90f766` and `8595c819`. Failures corrected before the final frozen candidate are
recorded as resolved below, not presented as current defects. Changes after this
report's hashes require their own verification; this report does not certify moving
workspace HEAD. Shared SDLC state and stage iterations remain coordinator-owned.

## Open Must Fix

### R2-1 — HIGH / Security: kill switch can be bypassed during preflight

Location: `kis_hl/managed_execution.py`, `Supervisor._step`, QUEUED branch: the
`entries_enabled` check before `gateway.preflight` and entry `_send` after it.
Requirement: MV3/MV5, kill switch blocks new entries while protection continues.
Confidence: high. Disposition: **open, Must Fix**.

Account and market reads may take time. Disabling new entries during those reads
changes `managed_supervisors.entries_enabled`, but the supervisor never checks
that flag again before committing and transmitting the new entry. The flag change
also does not invalidate the position's optimistic version, so `save` succeeds.

Reproduction using the existing `Gateway` and `plan` fixtures, private SQLite,
and the final frozen candidate:

```python
store = ExecutionStore(temporary_database)
gateway = Gateway()
worker = Supervisor(store, gateway, live=True)
row = store.enqueue('scope', plan(), live=True, now_ms=1)
original = gateway.preflight

def preflight(plan, now):
    snapshot = original(plan, now)
    store.set_entries('scope', False)
    return snapshot

gateway.preflight = preflight
worker.step(row['id'], 10)
```

Observed: `entries_enabled('scope') == False`, but sent kinds are `['entry']`.
This models an operator disabling entries while preflight is waiting on reads.

Required correction: recheck entry authorization, including the kill switch, at
the final submission boundary under a defined ordering/ownership contract. Prevent
a disabled flag from being ignored merely because an earlier preflight began while
enabled. Keep protective exits and reconciliation available. Add this regression
and an integrated concurrent disable/send test for the chosen linearization rule.

## C1–C9 recheck

| Earlier finding | Final bounded assessment |
| --- | --- |
| C1 queued cancellation submits entry | Resolved: cancellation/exit flags are checked before entry; regression passes. |
| C2 stale quotes bypass protection deadline | Resolved for the reproduced case: account exposure/order facts and first-fill deadline progress despite stale price; unavailable exit prices remain explicit. |
| C3 final exit stops reconciliation | Resolved in the final candidate: unresolved exits are reconciled; intervention now allows known-stop cleanup when flat. Reproduction after exit deadline and later fill reaches CLEANUP and creates a cancel attempt. Regression covers cleanup. |
| C4 rejected entry cancel waits forever | Resolved for the reproduced case: bounded retries and cancellation deadline produce intervention while original order facts remain reconciled. |
| C5 generic stop label certifies protection | Resolved across supervisor/gateway boundary: side, reduce-only and SL contract checks; gateway binds identity and Stop Market semantics. Negative gateway tests pass. |
| C6 cancellation crash loses exit intent | Resolved: `_send` persists triggering state before external actions; crash regression passes. |
| C7 lexical equal-time ordering | Resolved: supported position continuity orders same-time fills; ambiguous ordering remains pending. |
| C8 correction snapshot includes removed cycles | Resolved: snapshots use the effective replacement cycle set; regression gives one effective entry and trade count one. |
| C9 row count claims old retention completeness | Resolved for the reported old/empty-window case: current retained-tail evidence establishes a lower boundary and older intervals remain incomplete. The test does not prove live retention stability during a long fetch. |

## Additional challenges and resolved observations

- **Revoked/expired signal authority:** initially the supervisor did not recheck it.
  The coordinator added the check after preflight. A frozen-source reproduction
  enqueued under a grant, revoked it, allowed the signal to expire, then stepped
  the supervisor: INTERVENTION and zero entry submissions. Strategy tests also
  cover grant scope/budget/revocation and signal expiry.
- **Crash before attempt persistence:** an earlier candidate remained ENTERING
  forever with no attempt. The final candidate recognizes the write-ahead proof of
  no transmission and repeats preflight. Reproduction resumed with exactly one
  persisted entry attempt; later expiration requested cancellation. The new
  regression verifies recovery. This is distinct from UNKNOWN-after-send, which
  must continue to reconcile rather than blindly resend.
- **Gateway evidence:** current tests challenge client-ID recovery, native identity,
  stop semantics, missing quotes, foreign increases, broker quote clock/identity,
  KIS cancellation identity/quantity and cumulative fill handling. These are fake
  transports, not proof of account eligibility or live order behavior.
- **KIS NASD query scope:** the hardcoded query prompted a routing challenge.
  The coordinator supplied exact cached official-source references distinguishing
  all-US live inquiries from paper behavior. No finding is raised merely because
  an AMEX execution instrument uses a documented NASD all-US inquiry. This review
  did not independently fetch or re-open those upstream documents; final route
  documentation/tests must retain the endpoint/environment distinctions.

## Executed verification and limits

Final frozen run: **51 tests passed; 0 failures; 0 errors**, from
`tests.test_managed_execution`, `tests.test_journal_sync`,
`tests.test_journal_history`, `tests.test_strategy_signals`, and
`tests.test_managed_gateways`. The separate inline reproductions above additionally
challenged kill-switch timing, deadline cleanup and crash-before-attempt recovery.
The runner used `python3 -B`, in-memory frozen imports and private temporary SQLite.

Account lock functions were replaced with `nullcontext` inside the isolated test
process. Thus the tests exercise deterministic state transitions, not real
cross-process mutual exclusion. No API/account/order calls or credentials were
used. No source or shared SDLC state was edited; this report is the sole retained
write. No commits or further delegation.

The complete CLI, actual process concurrency, external venue behavior, durable
scheduling and final full-candidate smoke remain outside this bounded assessment.
The coordinator must close R2-1 with refreshed evidence and obtain final independent
candidate verification before claiming implementation readiness.
