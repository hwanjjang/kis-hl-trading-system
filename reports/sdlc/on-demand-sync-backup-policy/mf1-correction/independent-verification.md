# Independent implementation verification — PR19 MF1 correction

**Verdict: PASS for bounded independent implementation verification.**
No unresolved implementation findings were observed. MF1 formal review disposition
remains with the cross-provider reviewer; this report does not close that review. This is independent
implementation verification, not formal cross-provider PR review. The root agent
owns SDLC state/counters and publication. No additional delegation.

Baseline HEAD: `1343e90f2bfc44007c9a878b2f805cd6dd9a612c`.
Consumed review: `reports/sdlc/on-demand-sync-backup-policy/pr-review.md`, MF1.
Review file SHA-256: `9a9915e1019908b05dcad44b020ed37d88bfc8e5cd5f0d5ecffb5dc209af0a89`.
Consumed specification: `specs/account-audit.md`, initial SHA-256
`84eef73122b0c90c6582237086af9f8269dcc1922152e2cd077572a0c270ab8f`.

## Verification design

MF1 states that every positive-quantity domestic executed order must have a known
KIS buy/sell side and must be represented in normalized domestic facts/order IDs.
The initial missing-day/cost check allowed an unknown-side order to vanish when
its day/symbol key happened to exist. The correction must close capture and
normalization/compare paths while retaining zero-quantity unexecuted rows as
non-economic evidence.

The independent scratch probes use their own synthetic fixture builders and
provider stub, and real temporary SQLite. They do not import author test fixtures.
Independently exercised assertions:

- Unknown, missing, empty, null and wrong-type sides with positive executed
  quantity reject in the domestic adapter, compare and capture; compare leaves
  accounts, observations, facts, coverage, analysis and receipt counts unchanged.
- Both a zero-quantity daily snapshot with only an invalid executed side and a
  valid executed order alongside an invalid executed order reject.
- Identical side variants with order quantity zero do not become facts and do
  not invalidate otherwise valid capture/compare.
- Multiple days, symbols and both valid sides represent all and only positive
  executed order identities exactly once, preserve total quantity, and apply
  through the real revision/journal path.
- Positive orders still require corresponding daily and cost sources.

No network, credentials, operational databases, product edits, commits or external
publication are permitted or performed by this verifier. Only adjacent
`independent*` scratch/evidence files are owned. No new general skill observations;
this is task-specific correction verification.


## Actual checks and evidence

All commands below were executed by this independent verifier after the root
agent signaled the final candidate. No author test-fixture module was used by the
new MF1 independent probes.

| Command | Outcome | Evidence |
| --- | --- | --- |
| `PYTHONPATH=. python3 .planning/2026-09-13-account-journals/mf1-correction/independent_probes.py` | PASS, 9 tests, 0.471 s, exit 0 | Eight side variants (unknown code, empty, null, integer, boolean, list, object, missing) in positive and zero-order paths; multi-day/symbol/side coverage; orphan day/cost rejection; duplicate daily representation; rehashed invalid reports reject before any DB changes |
| `python3 -m unittest tests.test_account_audit tests.test_audit_capture tests.test_kis_order_coverage -q` | PASS, 55 tests, 2.528 s, exit 0 | Focused capture/audit/coverage behavior |
| `python3 scripts/smoke_account_audit.py` | PASS, 18 CLI subprocesses, exit 0 | Newly rejects malformed executed-side capture with no output bundle, compare with no report or DB change, and rehashed apply with no DB change; previous end-to-end flows retained |
| `PYTHONPATH=. python3 reports/sdlc/on-demand-sync-backup-policy/independent_probes.py` | PASS, 19 tests, 1.521 s, exit 0 | Prior independent concurrency, inventory, provenance, maturation, funding-grain, staleness and immutable-report regressions |
| `python3 -m unittest discover -s tests -t . -q` | PASS, 415 tests, 30.947 s, exit 0 | Full repository regression; output retained in adjacent `independent-full-suite.log` |
| `git diff --check` | PASS, exit 0 | No whitespace errors in current diff |

The independent valid population contained four positive executed orders across
two dates, two symbols and both sides, plus an unmatched zero-executed unknown-side
order. Normalization represented the four economic order identities exactly once,
quantity totaled 6, and explicit apply stored three daily-side facts. The
zero-executed row created no trade. Duplicate daily representation rejected.

For every invalid/missing side variant, compare and re-derived apply retained
identical row counts for accounts, facts, source observations, coverage, analysis
runs and collection receipts. A new file digest on the malformed plan did not
bypass source validation. No intermediate successful capture/report is emitted by
the exercised CLI negative scenarios.

## Inspection assessment

`validate_domestic_orders` obtains positive executed rows with decimal-safe
quantity parsing, requires daily/cost corroboration, and rejects any side outside
`01`/`02` before normalization. Both capture and the shared domestic normalizer
call it; audit reaches it through `domestic_bundle`, removing the prior duplicate
partial guard. A Counter comparison of date/instrument/side/order ID enforces
one normalized representation for each positive source order. Invalid input thus
rejects before revision or journal writes. Zero-executed rows remain non-economic
evidence rather than becoming trades.

Reviewed the operations and journal-contract documentation changes; they describe
the exact positive-order, side and coverage rules without implying independent
statement completeness. No live API behavior was tested or newly certified.

MF1's original zero-day and mixed-valid unknown-side reproductions are corrected
on this candidate. No new Must Fix or recommended findings arose within this
bounded correction. Formal cross-provider re-review and any publication remain
root/reviewer-owned.

## Consumed final candidate SHA-256

Baseline Git HEAD remains `1343e90f2bfc44007c9a878b2f805cd6dd9a612c`.
These hashes bind the uncommitted correction candidate. Product/test/smoke hashes
were checked before and after final executions and remained unchanged. Relevant
later edits require renewed evidence; a matching future commit can reuse it.

| File | SHA-256 |
| --- | --- |
| kis_hl/data_ingestion.py | 6d4a0b5cf4a809c4841fe83e9879f41056dc4771eb6ed83935f4c83713aaeb12 |
| kis_hl/data_account_audit.py | 1c20e3074b3d42477da5d6ccca6668bc074ae2d9a2109ec28e33840924faa0e6 |
| kis_hl/data_audit_capture.py | cb9a0d6c45d61001a95c9c8a6f3d0dfef53a5cad4acb6f5850392cf40fc994a0 |
| tests/test_kis_order_coverage.py | 2c53c08e780c75c1c5ee8b591fad614a8336fc1db4aa99b6b7cbd63d0b30fffb |
| tests/test_audit_capture.py | dcfcd2fd51b531d5496895e696c0b6ca600ea57321be68f41ea18d610d7eaf62 |
| scripts/smoke_account_audit.py | 153bb7d0b3117ddbfc884421279ace6456c3594555c899523d7b01897115d86c |
| specs/account-audit.md | 84eef73122b0c90c6582237086af9f8269dcc1922152e2cd077572a0c270ab8f |
| .agents/skills/trade-journal/references/record-contract.md | 20f555ab582d6551da7600cf1775ca03c2b586af5536f26ebcd4cf48ded931b6 |
| docs/unified-data-operations.md | 172ed46c393db23a9598d764e0ddaa576e9b856957c28ef9f241460ad4382b67 |
| reports/sdlc/on-demand-sync-backup-policy/pr-review.md | 9a9915e1019908b05dcad44b020ed37d88bfc8e5cd5f0d5ecffb5dc209af0a89 |

Final observation flush: no new generalized skill observations. Only bounded
independent scratch/evidence files were changed by the verifier. No external
systems, credentials, operational accounts or shared SDLC state were accessed.
