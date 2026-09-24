# Correction — binance-order-execution (2026-09-20)

| Field | Recorded value |
| --- | --- |
| Task / stage / owner | binance-order-execution / correction / main agent |
| Consumed inputs | pr-review.md (rounds 1–11), independent-verification.md (iterations 1–2), build.md iteration 4 |
| Candidate | head 7ffb790 on `binance-order-execution` (PR #18) |
| Status / decision | PROCEED — every Must Fix finding resolved and re-reviewed; deferrals recorded |

## Finding dispositions

| # | Source | Severity | Finding | Disposition | Resolution evidence |
| --- | --- | --- | --- | --- | --- |
| 1 | Codex r1 | P1 | conditional orders on /fapi/v1/order (-4120) | Must Fix, fixed 3bd980d | tests AlgoOrderRoutingTests; r2+ no repeat |
| 2 | Codex r1 | P1 | 5xx recorded as rejected | Must Fix, fixed 3bd980d (+097f353, 683c35b, a4510f7, bc454f4 refinements) | UnknownOutcome*, Reconciled* tests; r10/r11 clean |
| 3 | Codex r1 | P1 | reduce-only MIN_NOTIONAL | Must Fix, fixed 3bd980d | NotionalAndDirectionTests |
| 4 | Codex r1 | P2 | CONTRACT_PRICE direction | fixed 3bd980d | same |
| 5 | Codex r2 | P1 | 408/-1007 unknown | Must Fix, fixed 8b95376 + 097f353 | UnknownOutcomeCodeTests |
| 6 | Codex r2 | P1 | algo cancel symbol guard | Must Fix, fixed 8b95376 | CancelAlgoSymbolGuardTests |
| 7 | Codex r2/r3/r6 | P2 | account-wide algo listing (+ wrong path, incomplete flag) | fixed 8b95376, ae22acd, a4510f7 | CLI tests; route probe |
| 8 | Codex r3 | P1 | /fapi/v1/openAlgoOrders path | Must Fix, fixed ae22acd | unauthenticated probe 401 vs 404; test |
| 9 | Codex r4 | P2 | ALGO_UPDATE not parsed | **Deferred (Recommended)**: event schema not verifiable offline; documented open risk in docs/architecture.md; follow-up issue suggested | — |
| 10 | Codex r5/r8 | P2 | reconciled terminal / FINISHED algo stored active | fixed 683c35b, 1d7d3a4 | ReconciledStatusTests, CLI test |
| 11 | Codex r6 | P1 | partial fill classified rejected | Must Fix, fixed a4510f7 | ReconciledPartialFillTests |
| 12 | Codex r7/r8/r9 | P2 | cancel → local protective state; identifier exclusivity; env/account scoping | fixed ca59dae, 1d7d3a4, bc454f4 | CLI + storage tests |
| 13 | Codex r8 | P2 | .env.example demo profile | fixed 1d7d3a4 | — |
| 14 | Codex r9 | P2 | cancel outcome reconciliation | fixed bc454f4 | CancelReconciliationTests |
| 15 | QA it.2 | Should Fix | skill 5xx wording; binance-stop --exchange-test | fixed 7ffb790 | tests; Codex r11 clean |
| 16 | QA it.1/2 | Nits | exit codes for rejected/unknown; -2015 message echoes IP; client-id deactivation on reused ids; MARKET_LOT_SIZE step | Deferred (Nit) | listed in completion.md |

Reviewer resolution: each Must Fix was absent from the next Codex round on the corrected head; rounds 10 and 11 reported no defects.
