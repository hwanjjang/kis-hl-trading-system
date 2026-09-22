# Independent implementation verification — account audit

Date: 2026-09-21. Role: independent implementation verifier (`/root/verify_account_audit`).
This is not an eligible cross-provider PR review. Base and starting HEAD:
`f4c492e56aa4bb44f439ad5f56fc74fc1d3df8d2`. Branch: `docs/on-demand-sync-backup-policy`.
Scope: capture, read-only comparison, explicitly applied local revisions, selected
account/combined journals, source/identity/inventory/accounting safety and offline smoke.
No external requests, operational database reads/writes, commits, pushes or PR comments.
Only this report and its adjacent scratch probe script are verifier-owned changes.

## Current final verdict — corrected bounded inventory

**PASS** for independent implementation verification on the final hashes in the
last section. IV-01 through IV-04 are resolved. Independently rerun: 19 scratch
probes, 48 targeted tests, and 15-subprocess offline CLI smoke, all passed. No
unresolved mandatory findings. This remains separate from cross-provider PR
review and does not claim merge readiness. Earlier verdicts and candidate hashes
are preserved below as history.

## Historical failing verdict — iteration 3

**CHANGES_REQUIRED**. IV-04 is a new mandatory regression found in the bounded
inventory correction, described below. Iteration 2 PASS remains historical evidence
only; it does not cover the new candidate.

## Prior verdict — iteration 2

**PASS** for the bounded implementation verification scope. IV-01, IV-02 (including
inventory evidence), and IV-03 are resolved by independent correction inspection
and actual renewed executions. There are no unresolved mandatory findings. This
is not a cross-provider PR review or a merge-readiness assertion. Final evidence
and corrected candidate hashes are recorded below.

## Initial verdict — retained iteration 1 history

**CHANGES_REQUIRED**. Three independently reproduced mandatory findings below.
The author accepted all three and is preparing corrections. This verdict must not
be treated as PASS until the corrected candidate is independently re-executed.

## Inputs and method

Read AGENTS.md, CLAUDE.md ownership, task-observer, karpathy-guidelines, SDLC
verification/policy, trade-journal record/statistics contracts, and KIS/Hyperliquid
API skills. Read `intent/account-audit.md`, `specs/account-audit.md`, and
`plans/account-audit.md`. Inspected new audit/capture modules, CLI routing,
normalizers, store transaction and revision semantics, funding representation,
author tests and smoke. Synthetic temporary SQLite stores only.

Acceptance mapping: AC1 capture/compare database isolation (CLI smoke and targeted
tests); AC2 costs/funding/inventory/source differences (inspection and negative
probes); AC3 digest/staleness/corrections/atomicity (targeted tests plus concurrency);
AC4 replay/selected+combined journals/old reports (smoke, tests); AC5 offline full
flow (15 real subprocesses with synthetic provider I/O and forbidden sockets).

## Findings

| ID | Severity / category | Location | Evidence and impact | Requirement / confidence | Disposition |
| --- | --- | --- | --- | --- | --- |
| IV-01 | HIGH / inventory | `data_account_audit.inventory_findings` | At t=100, buy 1 from position 0 and sell 1 from position 1 produce an empty `roots - ends`. The warning followed by `break` skips all later rows and final holdings. Both a subsequent t=200 buy from position 50 and complete current holdings of 99 yield no blockers, so contradictory evidence can be applied. | AC2/AC3: contradictory inventory must block; high confidence | Must Fix; author accepted |
| IV-02 | MEDIUM / evidence integrity | `data_account_audit.normalize_bundle` | Original `hl_fills` evidence has fee 0.1 in matching raw/body; change only `sources[].data[].fee` to 9.9. Compare returns no blockers because raw is checked against its own body only, not the normalized source. Apply would link the revised economics to a bundle containing contrary provider evidence. | Source-backed comparison and rederived plan, AC2/AC3; high confidence | Must Fix; author accepted. Explicit operator input with evidence=[] is an allowed trust boundary, not broker authenticity. |
| IV-03 | HIGH / missing executions | `data_account_audit.normalize_bundle` / `domestic_bundle` invocation | KIS domestic source with days=[], one executed positive-quantity order, and costs={} produces changes=[],findings=[],blockers=[]. The existing domestic normalizer loops daily rows and ignores unmatched executed orders. A clean DB can receive a successful empty audit despite an explicitly observed execution. | AC2/AC3 and no silently fabricated coverage; high confidence | Must Fix; author accepted |

Reproduction: `PYTHONPATH=. python3 .planning/2026-09-13-account-journals/audit-implementation/independent_probes.py`.
Initial six independent probes: four failed (two for IV-01, one each IV-02/IV-03),
two passed (concurrent same-report apply and unrelated account isolation).

## Independently executed checks

- `python3 -m unittest tests.test_account_audit tests.test_audit_capture -q`: first
  execution 38 tests, two failures in author tests inserted concurrently as intended
  Red (`replay_with_different_journal_option_is_explicit`,
  `same_time_funding_with_distinct_ids_is_ambiguous`). Author acknowledged and fixed
  those independently of this review's three findings.
- `python3 scripts/smoke_account_audit.py`: PASS, 15 CLI subprocesses. Confirmed no
  operational DB creation during capture; read-only comparison; exact digest guard;
  selected two-account plus combined journals; no duplicate replay; USDC net 1.6
  and KRW net 2; partial coverage; explicit correction flag; stale rejection;
  immutable export; missing source rejection; private file mode.
- `python3 -m unittest discover -s tests -t . -q`: PASS, 399 tests, 26.687 seconds,
  exit 0 (intermediate candidate, before IV corrections).
- Concurrent two-thread apply of the same report, separate DataStore objects:
  exactly one first success, one already_applied, one fact revision, one journal,
  one collection receipt. PASS.
- Add an unrelated KIS account after comparing only a Hyperliquid scope: selected
  report still applies. PASS; unrelated account activity does not create false drift.
- Independent probes: 6 cases, 4 failed, exit 1, 0.272 seconds.

## Candidate identity at independent failing-probe execution

Hashes taken immediately before the six-case scratch execution. Author work was
ongoing, so this is an uncommitted candidate identity, not a final commit assertion.

| Path | SHA-256 |
| --- | --- |
| kis_hl/data_account_audit.py | 99ffb1d2d5cdd492b19e625209f0fafbaec0fdc57db8faaa26812c2574d971ab |
| kis_hl/data_audit_capture.py | b8d8a6982bb35ba3dc39b4898f5e804428c501ea9f0fb2d837dde753b4e58409 |
| kis_hl/data_cli.py | ce437e094563cf3871a6a04e27b69c165f59792b987e45ee35e87d9b8cbf11e6 |
| tests/test_account_audit.py | cd07054eb2b2512e91621d0c368028f285381a424b2af752397104e5976e0e61 |
| tests/test_audit_capture.py | 38de12eae9b376aa54a6e3e2901e30539c0222903f9e3e8b0f2af6d500b6c964 |
| scripts/smoke_account_audit.py | 3b4de810e5b6faa8d8167ae7aeacaf8487fde9a705732b0baaec6751869796a5 |

## Limitations and observation checkpoint

Live API shapes and retention were not verified; local provider transport was
synthetic. Hashes prove local content identity, not provider authenticity. No
operational accounts were used. Documentation was still being written by the main
agent; this report does not certify final documentation or cross-provider review.
Existing skill observation frontmatter/principles were scanned. No new general
skill observations arose; task-specific defects are recorded above. Shared
observation state was intentionally not changed under the bounded verifier scope.

## Additional inspection during author correction

- Added independent KIS order maturation and reverse DAY-to-POINT funding checks;
  both PASS. The former leaves one latest fact at revision 2; the latter selects
  exactly -2 cash despite retained immutable day and point representations.
- IV-02 residual independently reproduced after initial source-row binding was
  added: captured `hl_positions:` raw/body contains BTC size 99, but bundle
  `positions` is 1 with complete inventory and a matching buy 1 from 0. Compare
  still returned no blockers. Inventory is another source adapter input and must
  also bind to captured position evidence. Author notified; scratch test
  `test_inventory_adapter_cannot_disagree_with_captured_inventory` records it.
  This is an extension of IV-02, not a fourth finding.


## Iteration 2 correction assessment and renewed evidence

The author explicitly confirmed product edits complete before final candidate
binding. All three original findings remain in the history above and are closed
only by the following verifier checks:

- **IV-01 resolved**: a same-time closed cycle with a unique explicit zero anchor
  proceeds through every row and final holdings; ambiguous native anchors block.
  Both original independent negative inventory probes now PASS.
- **IV-02 resolved**: native decoded trade/funding rows bind to captured evidence;
  KIS daily costs additionally bind to day/symbol query parameters; inventory
  adapter values bind to native balances. Both trade-fee contradiction and
  inventory contradiction independent probes now PASS. No-evidence inputs are
  explicitly labeled operator supplied; provider authenticity remains outside
  the local JSON trust contract.
- **IV-03 resolved**: positive executed KIS orders require corroborating daily
  source/cost evidence before normalization, in capture and comparison. The
  independent orphan-order probe now PASS.

Final actual executions (all exit 0):

| Check | Result | Coverage |
| --- | --- | --- |
| Independent scratch probes, same command above | 10 PASS, 0.740 s | Four original failures, inventory evidence residual, concurrent duplicate apply, scope isolation, KIS daily identity maturation, reverse funding grain equivalence, immutable old report re-export |
| `python3 -m unittest tests.test_account_audit tests.test_audit_capture -q` | 46 PASS, 1.374 s | Capture, normalization, identity, report/apply, rollback, corrections, replay, negative validation |
| `python3 scripts/smoke_account_audit.py` | PASS, 15 subprocesses | Real CLI + SQLite with synthetic native provider I/O; network forbidden; no operational data |
| `python3 -m unittest discover -s tests -t . -q` | 406 PASS, 34.190 s | Full repository regression, corrected candidate |

The old-report check re-exported the **same saved report ID after a fact revision**
to a new file and compared bytes; it did not merely inspect an already-created
export file. Concurrent apply used separate SQLite connections and produced one
receipt, one revision and one analysis run. KIS maturation retained one current
fact at revision 2; funding conversion retained -2 selected cash with both source
representations preserved. All current report coverage remains partial/unverified;
no independent-statement certification is inferred from these API comparisons.

## Iteration 2 corrected candidate SHA-256 identities

Starting Git HEAD/base remains `f4c492e56aa4bb44f439ad5f56fc74fc1d3df8d2`.
The following content hashes bind this uncommitted implementation verification;
a later matching commit may reuse this evidence, while relevant edits require
renewed checks. The before/after corrected-product hashes were unchanged across
the final targeted, scratch, smoke and full regression executions.

| Path | SHA-256 |
| --- | --- |
| kis_hl/data_account_audit.py | 697e631f0814dbb796c84ae9a45cac33466aa72f976f2112e3d18e2681e925df |
| kis_hl/data_audit_capture.py | 3e7e69efddc6e4de0a21698580fed861cd0d78181b814efed678d079b5e745b6 |
| kis_hl/data_cli.py | ce437e094563cf3871a6a04e27b69c165f59792b987e45ee35e87d9b8cbf11e6 |
| tests/test_account_audit.py | 59aa6633977f68f9db1068a4113b839e65484a4b0c83d0ac1f793cc89ef0e930 |
| tests/test_audit_capture.py | 0bbf25a146b8e0339ad7d166baeb56826358c1dca68f9480cac28a812a2d094f |
| scripts/smoke_account_audit.py | 3b4de810e5b6faa8d8167ae7aeacaf8487fde9a705732b0baaec6751869796a5 |
| intent/account-audit.md | 2bece99021dee7e298a325fe2a0effeb8aea3e1350991305ac0be36b5fc6058d |
| specs/account-audit.md | 84eef73122b0c90c6582237086af9f8269dcc1922152e2cd077572a0c270ab8f |
| plans/account-audit.md | 269c8b79d80ff5b19c5bb1002c84f6d52a9f13b359fba82a4d4ecbd57ca09c41 |

Final observation flush: no new general skill observations; concrete task defects
and their resolutions are retained here. No shared state, product code, author
tests, external systems or operational accounts were modified by the verifier.


## Iteration 3 — bounded inventory correction

The proposed use of merged canonical and fresh trades is appropriate for a
funding-only bounded capture holding previously recorded inventory. Five new
independent probes verified the intended case and retained guards: successful
apply with one prior trade plus one new funding fact; missing saved fill inside
the requested interval still blocks; a prior native inventory discontinuity
blocks; changes to earlier canonical history stale the reviewed report; canonical
fills after requested end are excluded from ending inventory.

Existing 10 scratch cases and these five cases PASS (15 tests, 0.610 s).
The targeted suite passes 47 tests, and the 15-subprocess smoke passes.

**IV-04 — HIGH / inventory / Must Fix / high confidence.**
Location: `_compare` merged inventory input and `inventory_findings` early
`inventory_unanchored` exit. An earlier canonical portable statement without
`position_before` now causes the entire instrument check to stop before fresh,
fully anchored native fills. Reproduction: canonical HL buy at t=100 with unknown
position before; fresh t=600 buy 1 from 0 and t=700 buy 1 from 50; bounded range
[500,1000). Observed no blockers, only operator-supplied-source and
inventory-unanchored warnings. The fresh t=700 discontinuity was previously
rejected by fresh-only validation. This violates AC2/AC3 by allowing earlier
unknown history to conceal known contradictions. The independent scratch test
`test_unknown_old_inventory_cannot_hide_new_native_discontinuity` fails as intended.
Require continued independent validation of source-backed later segments (or an
additional fresh-row check that does not falsely demand source-range inventory
for funding-only captures).

Candidate SHA-256 for IV-04 reproduction:
- `kis_hl/data_account_audit.py`: `8eefc0fbef71f39b247f5d71fd299bfa65f491841d665cdebc44107182f02247`
- `tests/test_account_audit.py`: `90f7bf3103d150d6e5eabc0e4a686902e94981b070a172f98cef9bddbd1aac8d`
Other candidate hashes are unchanged from iteration 2. Initial IV-01–IV-03 remain
resolved; IV-04 is a separate regression introduced by the scope of history checked.


## Final IV-04 correction and independent closure

**IV-04 resolved.** Inspection confirms the inventory walker skips only unknown
initial timestamp batches while retaining the warning, resumes at a later
source-backed native position anchor, and checks complete snapshots only when
quantity has become known. Ambiguous native anchors remain blockers. This does
not infer an opening quantity or certify the skipped interval.

The original fresh-discontinuity reproduction now passes, as do independent
variants proving later canonical discontinuities and current snapshot mismatch
cannot hide behind an older unknown prefix. A clean later native anchor is
accepted with the unknown-prefix warning and `coverage_certified=False`.

Final independent commands and outcomes on the candidate hashes below:

- `PYTHONPATH=. python3 .planning/2026-09-13-account-journals/audit-implementation/independent_probes.py`:
  **19 PASS**, 0.949 s, exit 0. Includes all previous ten probes, five bounded-range
  carry-forward/missing/stale/conflict/cutoff probes, and four unknown-prefix
  regression/positive variants.
- `python3 -m unittest tests.test_account_audit tests.test_audit_capture -q`:
  **48 PASS**, 1.333 s, exit 0.
- `python3 scripts/smoke_account_audit.py`: **PASS**, 15 subprocesses, exit 0;
  synthetic provider transport, forbidden network, temporary database only.

The final full-suite execution is owned by the root agent; this verifier's
independent full-suite 406 PASS remains explicitly associated with iteration 2.
The final affected checks and smoke above were independently re-executed after
the bounded-inventory and IV-04 edits. No additional product edits were made by
this verifier. Before/after final audit-module/test hashes match.

### Final candidate identities (supersede earlier candidate tables)

| Path | SHA-256 |
| --- | --- |
| kis_hl/data_account_audit.py | c3a207c4dd519fc80ecbb073adce75dc141f5cc5a690155a1a091aa3622028ad |
| kis_hl/data_audit_capture.py | 3e7e69efddc6e4de0a21698580fed861cd0d78181b814efed678d079b5e745b6 |
| kis_hl/data_cli.py | ce437e094563cf3871a6a04e27b69c165f59792b987e45ee35e87d9b8cbf11e6 |
| tests/test_account_audit.py | ffd08593f8a288253f2ab2de7f4ab9119e3ee1a213d1f565da4d2e9561268b29 |
| tests/test_audit_capture.py | 0bbf25a146b8e0339ad7d166baeb56826358c1dca68f9480cac28a812a2d094f |
| scripts/smoke_account_audit.py | 3b4de810e5b6faa8d8167ae7aeacaf8487fde9a705732b0baaec6751869796a5 |

No unresolved mandatory findings remain. No new generalized skill observations;
task-specific regression evidence is preserved above and in the scratch probes.
