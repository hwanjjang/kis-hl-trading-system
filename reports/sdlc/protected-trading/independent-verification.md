# Independent correction verification

Reviewer: `/root/review_trading_plan`, separate from builder `/root`.
Date: 2026-09-12. Verdict: **PASS** for frozen candidate
`ac6f00c728121e5a3e56523e142b2040d1aef3d92cc14ca94a357875182b8820`.
Base: `9360b0cdd2753d5ca94ce052b03fd67d7b0c4af1`.

No remaining Must Fix findings were identified in this bounded correction review.
This is independent SDLC verification of the corrections following Anthropic PR
review 1. The alternate-provider reviewer still needs to assess the corrected PR
and author dispositions; this report does not replace that review or authorize
live trading, unattended deployment or merge.

## Inputs and frozen identity

All 56 actual candidate files matched their manifest SHA256 values before and
after execution. Independently hashing
`json.dumps(manifest['files'], sort_keys=True).encode()` reproduced the candidate
above. No moving candidate input was detected. The complete exact input map is
`candidate.json`, pinned below.

Read `pr-review-1.md`, `pr-finding-dispositions.md`, current correction diffs in
runtime modules/tests/operations documentation, relevant full supervisor/gateway/
scheduler control paths, and current build/self-verification records. This follows
the broader prior source review. Previous report is preserved byte-for-byte as
`independent-verification-108d.md`; the earlier 12f0 CHANGES_REQUIRED report also
remains retained. Earlier PASS reports do not certify corrections they predate.

## Actual independently executed checks

| Check | Actual result |
| --- | --- |
| `python3 -B -m unittest discover -s tests -t . -q` | Exit 0; 260 tests passed in 16.447 seconds |
| `python3 -B scripts/smoke_protected_trading.py` | Exit 0; 18 actual offline CLI subprocesses passed |
| `python3 -B reports/sdlc/protected-trading/independent-ac6f-probes.py` | Exit 0; all additional correction probes passed |
| `python3 -B reports/sdlc/protected-trading/independent-followup.py` | Exit 0; prior IV-1 and IV-2 regressions passed |
| Repeated candidate verification | 56/56 matches; independently reproduced candidate digest |

Real local account locks were used throughout. The unit suite retains its fixture
venue transports; smoke used actual CLI handlers and temporary SQLite. Supplemental
failed-sync testing called the actual CLI handler with only fixture transport,
fixture scope and bounded test sleep. The IV-1 probe used a real idle scheduler
process and ten actual lock acquisitions. No account/API requests were required.

## Correction findings and adversarial checks

**F1 — closed within the documented recovery contract.** Snapshot RuntimeError/
OSError failures now persist DEGRADED state and retain reconciliation. Three
consecutive failures or the grace duration latches exit and marks the special
read-outage intervention. A successful snapshot resumes cancellation/exit for
that intervention; semantic identity/ownership errors still remain manual.
The full regressions exercise transient below-stop recovery, repeated failures
and an existing identity intervention. Independent additional probes crossed
`protection_grace_ms` with only two failures and restarted the supervisor between
steps: the exit latch and original first-fill time persisted, and recovery sent
an exit while retaining the original exit clock. A separate UNKNOWN submission
survived repeated read failures, supervisor restarts and successful readback with
one UNKNOWN attempt and no replacement entry. No write uses failed snapshot data.
Exception class/count is retained without copying sensitive transport payloads.

**F2 — closed.** The native perpetual session branch explicitly covers both BTC
and ETH while retaining the no-dex requirement. The weekend ETH regression passed;
the trading-hours owner documentation now reflects 24/7 ETH. This does not broaden
arbitrary non-xyz perpetuals or verify live ETH exchange acceptance.

**F3 — closed.** Both unsuccessful and incomplete collections set the next attempt
from completion time using the configured interval, without creating successful
coverage. Manual synchronization may retry sooner. Full tests cover incomplete
retention pacing. Additional independent testing made the actual persistent CLI
handler encounter a transport exception: across two polls it collected once,
preserved null last-success, and scheduled exactly 10800000 ms after last-attempt.
A pre-migration four-column SQLite schedule retained its interval, success and due
time on construction; new failure metadata survived reopening, and interval
changes anchored to last-attempt. No source coverage was fabricated. The previous
idle-lock and attribution adapter probes also remain green.

**F7 — accepted portion verified.** Preview validation requires a KIS price step;
the added test passed and independent probes rejected zero, negative, NaN and
infinite steps. Read outages retain a safe exception classification. Broader
classification of semantic/preflight errors remains an explicitly limited
operator-diagnostics improvement, not a newly claimed feature.

**F8 — closed for new preflights.** The gateway records baseline_start_ms and the
supervisor persists it; snapshot history uses that same anchor. An independent
actual KIS history-route probe queued before KST midnight, preflighted after it,
and checked subsequent snapshot parameters: both queried date_from 20260913.
Older rows without this field deliberately use created_ms as documented.

Earlier C1–C9, R2-1, IV-1 and IV-2 were not reopened by the reviewed changes. The
kill-switch send boundary, durable UNKNOWN reservation and strict protective-stop
readback remain in place.

## Dispositions and practical limits

F4 remains a deferred operator-recovery limitation: `order recover` retries native
readback; it cannot prove non-transmission or bind an arbitrary native ID. The
operations document now requires broker-side inspection/exposure management,
retains the intent reservation and prohibits SQLite retry edits. This deferral
must be assessed by the returning PR reviewer. It does not permit relying on
unattended KIS entries after ambiguous acknowledgments.

F5's action-expiry coupling is now documented. F6's conservative pending journal
behavior and F9's target-design diagram status remain documented deferred
recommendations. This bounded verification neither implements nor certifies those
future workflows. No browser rendering was repeated for unchanged diagrams.

PT1–PT5 corrections have passing local evidence; PT6 independent correction
verification passes, while alternate-provider PR reassessment remains pending.
Live order acceptance, partial fills, gaps/halts, cancellation reservations,
quote-clock rollout and exact KIS journal completion without source statements
remain outside these offline checks.

One nonblocking artifact observation: repository-wide `git diff --check` reported
trailing whitespace in generated `reports/sdlc/protected-trading/change-record.patch`
at lines 8218, 8219 and 8230, including a terminal blank line. This patch receipt is
outside the 56-file runtime/document candidate; no candidate-source whitespace
finding was reported. It is not evidence of a behavior failure.

No credentials, APIs, order/cancel/amend calls, source edits, shared SDLC writes,
commits or delegation occurred. Writes are this review, preserved reports and
sanitized local evidence only.

## Input and execution evidence hashes

| Path | SHA256 consumed/retained |
| --- | --- |
| `candidate.json` | `e2e06d21211afe9b85e7e342c40be6206ea11f433d082fa51812f55f6c4cf811` |
| `pr-review-1.md` | `d55657e562ebd4d0ed1bdb517c2b48f3b97c5dccc29bf5bb18809342e2d45a1a` |
| `pr-finding-dispositions.md` | `e891b7e21a4a8b889fe33d495a7316a04c2f615afed42f8b1f014ecd8e288f5b` |
| `build.md` | `4e0501bf0f04a0c831b7e7df5648b13341436ad776c857d300ebb35e4d0a6300` |
| `self-verification.md` | `450bf762f88967536b6b12a5f5f4e1222762207d38eed7557c060d6c2e097671` |
| `test-results.json` | `7a501456f940130d4c43cbcf7de6faef8212b4a1f6f75aa8fb40cf51a775dbce` |
| `artifacts.json` | `1a7289615a04fe09e92c5c76921d22e237ba6da2f6f907b0f4ae5957a680419d` |
| `independent-ac6f-probes.py` | `aff7e082a371c5d69552e1025f45d413d0144ca41c5e9c4f21437e11c60486a3` |
| `independent-followup.py` | `9afb86703765105fae2dfbc7ae184a334ade5652adeb84afc859f31ac69bbb4d` |
| `independent-verification-108d.md` | `fc2586e4e6a79a82724e37a5db873e472c337e63c8957952ef1124d17cfcc38f` |
| `independent-ac6f-unittest.txt` | `f02d1dacc91ffa9fd0af70a12db2075f9477cfd50d4207e2ff0e9f803ebd38a7` |
| `independent-ac6f-smoke.json` | `1066929385350eec10beeee37d1dbeba4b9e6c7357a0d5800ed11051279f31f7` |
