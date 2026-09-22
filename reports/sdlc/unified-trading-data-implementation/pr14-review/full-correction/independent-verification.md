# Independent implementation acceptance verification — iteration 3

**Verdict: FAIL — three reproduced corrections remain required.**

Candidate `sha256:9ae1292c578dc261fdac3b2d2fe0a120569b629ea3e7b93a2cdc847ad256a34b` over base `6d66b85971b7dfd5c2c7fef2ab2500cf4659f15e`. All 22 supplied file hashes matched. This is distinct non-builder implementation verification, not another PR-review attempt or a merge-readiness claim.

The independent execution passed **344 tests** and the **12-process real CLI smoke**. Targeted counterexamples exposed the three failures below; passing the existing suite does not establish their acceptance.

## Findings

### IV3-F1 — HIGH — required

**Bounded reconciliation omits authoritative realized PnL from its economic comparison.** `kis_hl/data_reconciliation.py:16`

Synthetic native HL buy at 100 and sell at 110: canonical closedPnl=999; independent statement closedPnl=10. All other fields agree. reconcile(apply=True) succeeds; the resulting journal is FINALIZED with net_pnl=999.

The newly added evidence-certification path certifies financial economics contradicted by the supplied independent statement.

Required correction: Include all authoritative economics used by journal calculations in reconciliation comparison, including gross_pnl/closedPnl; treat absent versus supplied authoritative fields explicitly. Reject disagreement before coverage or anchors are committed.

Reproduce: `PYTHONPATH=. python3 .planning/verification_probes.py`. Confidence: high.

### IV3-F2 — MEDIUM — required

**A recovered flat-anchored HL cycle still shares subsequent funding with the abandoned invalid segment.** `kis_hl/journal_exports.py:88`

Buy at t=10 starts position. Another buy at t=20 reports native position_before=0, proving the previous segment has a gap. Sell at t=30 closes the new cycle. Funding -1 at t=25 is assigned to both the earlier invalid OPEN cycle and the recovered cycle, so the latter remains PENDING despite having no other reasons.

The accepted flat-anchor recovery fix fails for ordinary funded perpetual positions; the abandoned invalid cycle has no end bound and contaminates all later funding allocation.

Required correction: Bound the invalid segment at the evidenced recovery boundary for allocation purposes without fabricating an economic close or finalized return. Preserve skipped fees and the gap finding. Funding after the new zero anchor must belong only to supported later cycles.

Reproduce: `PYTHONPATH=. python3 .planning/verification_probes.py`. Confidence: high.

### IV3-F3 — MEDIUM — required

**A collector append between journal reads and pinning is hidden by the post-read input watermark.** `kis_hl/data_store.py:183`

A deterministic interleaving adds funding -2 immediately before the journal calls its original pin implementation. The first report has net 10, regenerated report net 8, yet stale_runs remains empty because pin records a max fact ID already including the unread funding.

Concurrent scheduled collection can defeat the new late-fact freshness signal. Frozen historical reports must remain immutable; the failure is the missing current-projection stale signal.

Required correction: Tie fact/coverage watermarks to the journal input read boundary or a consistent read snapshot, rather than the later pin transaction. Ensure append and coverage changes during calculation still flag the old run; do not introduce long write transactions.

Reproduce: `PYTHONPATH=. python3 .planning/verification_probes.py`. Confidence: high.

## Acceptance coverage

The acceptance themes below cover all supplied twelve-defect correction scope and the additional operational workflows, without inventing a one-to-one mapping to unavailable historical finding IDs.

| Theme | Result | Evidence |
| --- | --- | --- |
| Portable statement cost and settlement contradictions | PASS | Full regression suite rejects inconsistent component/settlement rows; native numeric handling retained. |
| Positive KIS overseas quantities | PASS | Zero/negative quantities rejected as validation errors. |
| Ambiguous duplicate daily identity in one observation | PASS | Duplicate rows reject before fact writes; raw observation retained; repeated unique observations dedupe. |
| Monotonic KIS daily/cumulative maturation | PASS | Regression polls increase quantity from 1 to 2 as a revision; decreases remain unresolved. |
| Domestic multi-order grouped pending and other-market progress | PASS | Grouped quantity/cost retained with shared allocation reason; overseas collection continues. |
| HL recovery at explicit zero anchor and fee conservation | FAIL | Basic native-flat cases pass, but subsequent funding is contaminated by prior invalid segment: IV3-F2. |
| Bounded statement completeness, inventory and trust | FAIL | Operator trust limit documented, digest/range/quantity checks and rollback tested; authoritative PnL comparison missing: IV3-F1. |
| Late facts/coverage freshness and immutable exports | FAIL | Sequential late facts work and CLI exports stay immutable; concurrent append before pin defeats watermark: IV3-F3. |
| Current derived input validation and historical as-of behavior | PASS | Independent positive probe accepts old as-of input then rejects current superseded dependency. |
| KIS overseas book response blocks and clocks | PASS | Price/size read from output2, clocks retained from output1; regression tested. |
| Index price basis isolation | PASS | New index bars use index basis/raw adjustment; old variants deliberately preserved. |
| HL network collision guard | PASS | Independent probes reject testnet/custom endpoints before any book request or fact write. |
| New overseas minute adapter and bounded pagination | PASS_OFFLINE | New route and NEXT/KEYB semantics match public official sample; timezone, repeat-page rejection and transport tests pass. No live entitlement/history guarantee. |
| Scoped journal SQL reads | PASS | Only selected account trade/cash facts requested; regression asserts query calls. |
| Read-only status and schema preview | PASS | Independent hash/mode check unchanged on existing DB; absent path not created; drift rejection regression passes. |
| Recurring overlap, history audits and partial-success cursor | PASS | Unit regressions verify bounded overlap, independent audit mode and no success advance for partial collections. |
| Worker heartbeat without due jobs | PASS | Independent probe updates heartbeat from 1000 to 2000 without jobs. |
| Metric exclusion visibility | PASS | Code exposes excluded count/reasons and exact holding eligible count while preserving formula contract. |
| Operations/docs acceptance ledger | PASS | Outstanding broader design features are acknowledged as outstanding rather than silently accepted or waived. |
| End-to-end local operational smoke | PASS | 12 real CLI processes: absent status, import preview/apply, bounded reconcile preview/apply, journal, export, stale status, backup/restore; credentials/network disabled. |

## Independent commands and evidence

- Full suite: `python3 -m unittest discover -s tests -t . -q`; 344 passed in 19.485 seconds. See `.planning/independent-tests.txt`.
- Real CLI smoke: `python3 scripts/smoke_review_corrections.py`; 12 subprocesses passed, no network/private data, temporary files cleaned. See `.planning/independent-smoke.json`.
- Counterexamples: `PYTHONPATH=. python3 .planning/verification_probes.py`; full results in `.planning/probe-results.txt`.
- Additional positive cases: `PYTHONPATH=. python3 .planning/positive_probes.py`; absent DB previews, existing DB hash/mode unchanged, idle heartbeat, endpoint guard before requests, historical as-of preserved/current stale derived input rejected. See `.planning/positive-results.json`.

The [official KIS minute sample](https://raw.githubusercontent.com/koreainvestment/open-trading-api/main/examples_llm/overseas_stock/inquire_time_itemchartprice/inquire_time_itemchartprice.py) documents NEXT=1 and KEYB based on the prior oldest minute. No confirmed transport finding is raised solely from its generic tr_cont recursion. Live broker verification remains outside this task.

## Limits

- No live/account API requests, secrets/private account data, publication, commits, source edits or shared workflow mutations.
- Tests are offline, using temporary SQLite and synthetic source rows; broker update cadence, entitlement and history depth remain unverified.
- No speculative tr_cont transport defect asserted: official sample explicitly defines NEXT/KEYB but also contains generic continuation recursion; live transport was not exercised.
- Broader outstanding accepted-design work is outside this bounded correction verification; no overall project-complete or PR-review gate claim.
- Prior pass knowledge used only as regression context; builder results were not used in lieu of running checks.

Verifier: `/root/codex_full_review_1`, OpenAI Codex based on GPT-6, distinct from builder. Exact backend model ID and reasoning effort are not surfaced by this context. Product source was not modified. Parent was notified promptly of each concrete failure.
