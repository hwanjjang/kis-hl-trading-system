# Independent implementation verification

Reviewer: `/root/review_trading_plan`, separate from builder `/root`.
Date: 2026-09-12. Endpoint: local verification supporting a later PR.
Verdict: **CHANGES_REQUIRED** for candidate
`12f0febcf9fc5b638366f9f25e723b122e0beac0838597559faaa24ce6462a27`.

Two reproducible functional requirement violations remain against this candidate.
The coordinator accepted both and started corrections; those moving-source changes
are not certified by this report. This is independent implementation verification,
not the later Anthropic PR review, live-order acceptance or merge authorization.

## Candidate and input identity

Initial candidate:
`e6d357fed71de32b8fdccd4b757bf74ef0e64b653e50a8aa5ee21d0e2138babe`.
Base: `9360b0cdd2753d5ca94ce052b03fd67d7b0c4af1`.
All 53 manifest files initially matched their SHA256 values. Independently hashing
`json.dumps(manifest['files'], sort_keys=True).encode()` reproduced the candidate ID.

During verification, the coordinator superseded that candidate with `12f0…`, adding
the managed stop execution-price buffer, its regression assertion and operations
documentation. All 53 files again matched the new manifest at the next full-suite
start. The exact input hashes are retained in `candidate.json`, whose SHA256 at
that point was `01fd8b5c75993b306b98fcf17ccaaaccfe05915a86c9d88dda67c1147f3e955d`.

Inputs reviewed: canonical protected-trading intent/spec/plan and referenced
multi-venue design; `docs/trading-operations.md`; candidate/build/self-verification,
test-results and artifact records; changed modules/tests and integration diffs;
KIS managed-route reference, journal contract, workflow and smoke script.
Generated diagrams remain proposed views, with reused rendering receipts owned by
the coordinator; this review did not rerun the browser renderer.

**Moving-source qualification:** at the end of the full-suite run on `12f0…`,
`tests/test_journal_sync.py` no longer matched the manifest. Before the later
reproduction-script rerun, `operations_cli.py` had also received the scheduler fix.
Consequently, the passing executions cannot be promoted into a final frozen-source
PASS. The coordinator confirmed independent-verification iteration 2 was closed
BLOCKED before build iteration 3 corrections. Shared state was not edited here.

## Must Fix findings

### IV-1 — MEDIUM / Bug: idle scheduler excludes requested synchronization

Location in candidate `12f0…`: `kis_hl/operations_cli.py:404–458`,
`cmd_journal_sync`, the account-lock context surrounding the entire scheduler loop.
Related requirements: PT3 and MV4/MV5. Confidence: high.
Disposition: **accepted by builder; open for this candidate**.

The persistent `journal run` worker holds the synchronization lock during idle
sleep, not just collection. A separate requested `journal sync` can therefore
never acquire the same lock while the scheduler is running, even between its
three-hour jobs. Serialization becomes permanent exclusion of the requested path.

Independent reproduction used an actual CLI process and real local locks:

1. Create temporary SQLite with a fixture testnet account and set next due three
   hours ahead using `SyncSchedule.success(now)`.
2. Start `journal run --venue hyperliquid --account FIXTURE --start-ms 0
   --poll-seconds 1` in a temporary working directory, with only fixture environment
   values. The future due time prevents all vendor calls.
3. Confirm the journal lock is held, then run the actual separate CLI
   `journal sync --venue hyperliquid --account FIXTURE --start-ms 0 --end-ms 1`.

Observed: the requested command exited **1** with
`{"error": "Account has another execution owner"}` before any history request.
The scheduler remained alive and idle. No handlers or locks were mocked.

Required correction: hold the account collection lock only across the bounded
sync/cursor transaction; release it during idle wait. Recheck due state after
acquisition and define bounded contention behavior so multiple schedulers cannot
duplicate jobs. A requested run must be possible between scheduled runs.

The later moving-source reproduction found the idle lock available, consistent
with the coordinator's in-progress fix. Closing IV-1 requires the new candidate,
not a retroactive PASS for `12f0…`.

### IV-2 — MEDIUM / Bug: later evidenced attribution blocks automatic replay

Location: `kis_hl/journal_history.py:162`, `attribute_fill`, together with
`kis_hl/journal_sync.py`, `JournalLedger.ingest` conflicting-payload branch.
Related requirements: PT2 and MV4. Confidence: high.
Disposition: **accepted by builder; open for this candidate**.

A fill may first arrive while its managed order's native ID is unresolved. It is
correctly imported as unassigned. Once order reconciliation establishes that ID,
`attribute_fill` enriches the same execution with strategy/origin/version evidence.
`ingest` compares the entire serialized payload and treats this metadata enrichment
as an unauthorized economic correction. The automatic sync then rolls back the
whole batch on every overlap replay, preventing further progress until manual repair.

Independent reproduction, using only real local domain/storage functions:

1. Import execution `execution-1`, BTC buy 1 at 100, time 10, fee 0, native order 42,
   position-before 0; no matching managed native order exists yet.
2. Persist a managed position and entry attempt created at time 9. Reconcile that
   attempt to native order 42 in the same scope, without submitting any order.
3. Run `attribute_fill` again and ingest the resulting fill with normal automatic
   settings (`allow_corrections=False`).

Observed: `ValueError: Conflicting execution requires explicit correction import`.
Quantity, price, fee, timestamp, native execution identity and order identity were
unchanged. Only now-supported attribution changed.

Required correction: distinguish economic source changes from narrowly allowed,
monotonic, evidenced attribution enrichment. Preserve the source/evidence revision,
update effective cycle attribution idempotently and keep conflicting economic or
contradictory attribution changes behind explicit review. Do not broadly enable
automatic corrections merely to make this case pass.

## Retained reproducible evidence

`reports/sdlc/protected-trading/independent-reproductions.py` contains bounded,
offline regression probes for both findings. SHA256:
`252fb093c73bdaf92b9ab8225c51c9c5e98d025f7d8c867d3ec548e3ce612c32`.

Run `python3 -B reports/sdlc/protected-trading/independent-reproductions.py`.
The reusable scheduler probe checks the actual local lock while a real scheduler
process is idle, so rerunning it after a fix cannot accidentally reach a vendor.
The attribution probe executes actual SQLite/domain logic. All temporary state
and the scheduler subprocess are cleaned up. Its later moving-source execution
reported IV-1 passing and IV-2 still failing; that result is evidence for follow-up,
not a candidate-bound final verdict.

## Completed independent checks

| Check | Actual result |
| --- | --- |
| Initial `e6d357…` manifest | 53/53 SHA256 matches; candidate digest reproduced |
| `python3 -B -m unittest discover -s tests -t . -q` | 251 passed, 0 failures/errors, 15.972s on initial candidate |
| `PYTHONDONTWRITEBYTECODE=1 python3 -B scripts/smoke_protected_trading.py` | Passed: 18 actual offline CLI processes, temporary SQLite, zero vendor calls/orders |
| Refreshed `12f0…` manifest before full tests | 53/53 matches; candidate digest reproduced |
| Full suite repeated after stop-price change | 251 passed, 0 failures/errors, 12.980s; end check detected the subsequently edited journal test |
| Refreshed local smoke | Passed: all 18 processes; no mocked CLI handlers or locks |
| R2-1 kill switch | Closed: final pre-send check and regression block entry when disabled during preflight |
| C1–C9 earlier core findings | Targeted regressions pass; final-candidate review retains the implementation limits below |
| Stop execution-price buffer | New managed stop observed with trigger 96 and execution limit 95.04 for configured 1% slippage; buffer assertion passes |

Repeated full-suite captured output SHA256:
`0a414ed444ec9dab95e621798038ea0dc299c8fc351fa5b8dc4d0e3e40023c54`.
The unit suite retains its intentional fake vendor transports. This verifier did
not replace account locks or CLI handlers. Existing process-lock tests and the
additional real-process scheduler reproduction exercised actual local file locks.

## Acceptance and limitations

PT1 account/route/identity behavior has offline transport and gateway coverage;
unverified native KIS protection and paper restrictions remain explicitly gated.
PT2 is not complete because of IV-2. PT3 is not complete because of IV-1. PT4/PT5
have passing durable intent, partial-fill, stop-readback, cancellation, recovery,
ownership and grant regressions; the earlier kill-switch finding is resolved.
PT6 cannot be closed until the corrected, frozen candidate receives refreshed
independent evidence. The later provider-eligible PR review remains separate.

No live API, account lookup, venue order/cancel/amend, notification or deployment
was exercised. No signing credentials were used. No product source or shared SDLC
state was edited, and no commit or further delegation occurred. The only retained
writes are this report and its sanitized offline reproduction script.

KIS exact journal completion still requires source execution/cost statements.
Venue acceptance, gap execution, cancellation reservations and quote-clock rollout
remain operational verification limits rather than claims established by these
offline checks. A matching manifest, full-suite/smoke rerun and both retained
regressions must pass on the new candidate before a final independent PASS.
