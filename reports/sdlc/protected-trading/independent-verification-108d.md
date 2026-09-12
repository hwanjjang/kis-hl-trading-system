# Independent implementation verification

Reviewer: `/root/review_trading_plan`, separate from builder `/root`.
Date: 2026-09-12. Verdict: **PASS** for frozen candidate
`108d96a2f15e2825ff0d223db6e33740accc87f8b577f2dceb94c4071aaddd9f`.
Base: `9360b0cdd2753d5ca94ce052b03fd67d7b0c4af1`.

No remaining Must Fix findings were identified within the reviewed scope.
This closes the independent implementation verification stage for this candidate;
it is not the later alternate-provider PR review, live-order acceptance, merge
approval or deployment authorization.

## Identity and scope

All 53 actual source, test and document files matched `candidate.json` before and
after this follow-up. Independently computing SHA256 of
`json.dumps(manifest['files'], sort_keys=True).encode()` reproduced the exact
candidate ID above. No moving source inputs were detected in this run.

Review accumulated across the core and final assessments covers the complete
changed modules/tests and integration diffs, canonical intent/spec/plan, operations
documentation, relevant venue/journal owner references, build/self-verification,
test results and artifact records. The focused final follow-up reviewed the
scheduler lock scope, monotonic attribution revision logic, actual Hyperliquid
adapter opt-in and final entry transmission boundary. The earlier assessment of
candidate `12f0febcf9fc5b638366f9f25e723b122e0beac0838597559faaa24ce6462a27`
is preserved unchanged as `independent-verification-12f0.md`; its verdict remains
CHANGES_REQUIRED. Its old default-ingest reproduction intentionally remains strict;
the new follow-up exercises the real automatic adapter path.

## Actual independent executions

| Command/check | Result |
| --- | --- |
| `python3 -B -m unittest discover -s tests -t . -q` | Exit 0; 253 tests passed in 17.386 seconds |
| `python3 -B scripts/smoke_protected_trading.py` | Exit 0; 18 actual offline CLI subprocesses passed |
| `python3 -B reports/sdlc/protected-trading/independent-followup.py` | Exit 0; both retained findings resolved |
| Frozen manifest validation, repeated after all executions | 53/53 file hashes match; candidate digest matches |

The unit suite uses its existing fake venue transports. This reviewer did not
replace local locks or CLI handlers. Smoke ran actual CLI/parser/SQLite paths;
the additional scheduler scenario ran an actual idle CLI scheduler and ten real
lock acquisitions in another process. The automatic history scenario used actual
`sync_hyperliquid`, `attribute_fill`, execution storage and journal storage with an
in-memory fixture history provider. No network or account calls were made.

## Finding dispositions

- **IV-1 closed:** the scheduler acquires its lock inside each iteration, rechecks
  due state under that lock and releases it before ordinary idle sleep. Contention
  in persistent mode retries; requested/once mode still reports an active owner.
  With a future due time, all ten independent real lock acquisitions succeeded
  while the actual scheduler stayed alive. Collection serialization therefore no
  longer permanently excludes requested synchronization between scheduled runs.
- **IV-2 closed:** only the actual Hyperliquid adapter enables attribution
  enrichment. Initially unassigned fill execution-1 was imported, then a matching
  managed native order was established locally. A second real adapter sync added
  exactly one source revision with evidenced strategy/origin, preserving all
  economic fields. A third sync created no duplicate revision. Changing the
  execution price was rejected as requiring explicit correction and rolled back;
  revision count remained two. The suite also checks unknown replay cannot erase
  known attribution and contradictory strategy attribution stays rejected.
- **R2-1 closed:** entry enablement is checked after preflight and again inside
  `_send` after durable attempt creation, immediately before gateway dispatch.
  Disabled entries are durably rejected without submission. The preflight-change
  regression passed in the full suite. Signal/grant authority is rechecked after
  preflight reads, before entry transmission.
- **C1–C9 remain closed:** reviewed fixes and passing regressions cover queued
  cancellation, stale-data fill/deadline handling, continued exit reconciliation,
  cancel rejection, exact stop readback semantics, persisted exit intent across
  crashes, execution ordering, correction cycle counts and retention evidence.
- **Native stop execution buffer verified:** configured slippage produces a
  separate tick-rounded bounded execution price (trigger 96, execution 95.04 at
  1% in the regression). This checks the intended payload, not actual gap fills.

## Acceptance and limits

PT1 has offline account/route/identity and gateway coverage with unverified native
KIS protection and paper restrictions still gated. PT2 covers actual-fill facts,
fees/funding, coverage gaps, revisions, deduplication and late attribution. PT3
covers persistent configurable 10800-second scheduling and collection ownership.
PT4/PT5 cover durable attempts, UNKNOWN handling, partial protection, stop readback,
exit/cancel recovery, multi-position ownership and bounded signal/grant authority.
PT6 local independent verification passes; the separate PR review is still pending.

No credentials were read and no venue request/order/cancel/amend, notification,
commit, deployment or further delegation occurred. Product source and shared SDLC
state were not edited. Retained writes are reviewer reports and sanitized evidence.
Generated diagrams were checked in the prior design review; this implementation
follow-up reuses the builder's rendering receipts and did not run a browser.

Live partial fills, gaps/halts, exchange acceptance, cancellation reservations and
quote-clock rollout remain unverified. KIS exact journal completion still requires
source execution/cost statements. These explicit operational limits are not removed
by the offline PASS.

## Exact consumed identities and evidence

The complete 53-file input map is the independently checked `candidate.json`.
The following hashes pin supporting inputs and this verifier's retained evidence.
Shared stage receipts may subsequently change when the builder records this result.

| Path | SHA256 at consumption |
| --- | --- |
| `candidate.json` | `1ff6264d3b03f9a4fc0561a7943914896612433c011bde0301c5b1914a345e0a` |
| `build.md` | `99252a4a81748b94c38442ed16e25c0d0d2fec2ad260343568927bef5dfd611a` |
| `self-verification.md` | `56f9572af58ad10e86757e028cda74bd26c9d82677530af6c1e40150d5ef7429` |
| `test-results.json` | `30d6dccc945d18133a095a085101504bf21bef69f807a639f223037806ac5521` |
| `artifacts.json` | `a98340302c350ed8891fcf31ac239a0543936a38ef6ba3631d1b0c5566f1cc0c` |
| `independent-followup.py` | `9afb86703765105fae2dfbc7ae184a334ade5652adeb84afc859f31ac69bbb4d` |
| `independent-reproductions.py` | `252fb093c73bdaf92b9ab8225c51c9c5e98d025f7d8c867d3ec548e3ce612c32` |
| `independent-verification-12f0.md` | `5ba62f2ae8aedd183156591fab975c8f4083f775d049415e5b46e22afee555c4` |
| `independent-108d-unittest.txt` | `527bb4c306728b3112572cb69212e5ab0f8c7e9ff5ae3c368deb3323a88b36cc` |
| `independent-108d-smoke.json` | `1066929385350eec10beeee37d1dbeba4b9e6c7357a0d5800ed11051279f31f7` |
