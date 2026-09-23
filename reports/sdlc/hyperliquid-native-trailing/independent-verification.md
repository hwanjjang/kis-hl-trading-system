# Independent Verification: Hyperliquid Native Trailing

Verdict: **PASS for the final local runtime and documentation candidate**. No unresolved mandatory findings. This does not verify live exchange behavior or constitute a PR review, deployment approval, or completion of the implementation owner's separate diagram/SDLC artifact checks.

## Identity and scope

Reviewer context: `/root/native_trailing_review`, a fresh delegated Codex context, independent of implementation author `/root`. Provider: OpenAI; model and effort inherit the parent session and were not independently attested. This is local independent verification, not a cross-provider PR-review receipt. Endpoint: local. Shared stage attempt: 1; the precision correction was reviewed during this ongoing attempt.

No product edits, live trading, signed network requests, commits, pushes, issue actions or PR publication were performed. Reviewer writes are limited to this report and isolated `/tmp` verification fixtures.

Verified at: 2026-09-22T10:48:08.530793+00:00. Base: `94e8e9d15c28f37d91d2b8c1f82e593aaeb7f0e5`. Runtime candidate: `sha256:e11decf17076d5a381bab69bce228cf9a7790546d1ebe6db6b1784bac0d46231`. Independently recomputed all seven file hashes in `candidate.json`; all matched before and after final tests.

## Evidence examined

Read repository instructions, SDLC policy and verification contract, Hyperliquid API, Karpathy and task-observer skills; canonical task intent, spec, plan and investigation; actual tracked/untracked changes in client, trailing helper, managed gateway/supervisor and instrument capabilities; tests and offline smoke script. Reviewed README, operational guidance, architecture documentation and API skill reference changes. Independently inspected retained official app bundle functions `ace`, `s4`, `l4`, `oce`: these support action shape, signed field order, trigger-condition interpretation and ordinary cancellation, but do not establish a live acknowledgement or order-status response contract.

The final public-read change uses the existing `HyperliquidInfoClient.clearinghouse_state(dex=...)` path and is covered by the updated fixtures. SDK signing remains delegated to the official SDK.

## Findings and resolution

| Severity | Category | Location | Finding, evidence and impact | Related requirement | Confidence | Disposition |
|---|---|---|---|---|---|---|
| HIGH | Managed precision | `kis_hl/managed_execution.py`, native attempt submission | Initial candidate sent raw `trail.distance`; the client rejects tick/significant-figure violations. Ordinary ATR decimals could fail after entry and become UNKNOWN/manual intervention. Original native tests used distance 4. | AC2/AC3: usable safe native submission and recovery | High | **Resolved by reviewer**: managed distance now rounds down to the observed tick, refuses zero, persists the actual distance and matches readback against that persisted value. The added precision regression and final focused suite pass. |

No other mandatory defect found. The fixed stop remains independent of native trailing, local nine-minute behavior remains the default, and ordinary reduced exposure does not trigger trailing recreation or watermark reset.

## Actual final executions

Environment: local Python 3.12; offline exchange fixtures; real SQLite. Account-lock files isolated with `TMPDIR=/tmp/native-trailing-verifier-tmp` because concurrent builder tests use the same fixture account names.

| ID | Requirement | Layer and exact command | Actual result |
|---|---|---|---|
| IV-FINAL-UNIT | AC1–AC3 | `TMPDIR=/tmp/native-trailing-verifier-tmp python3 -m unittest tests.test_native_trailing tests.test_hyperliquid_client tests.test_managed_execution tests.test_managed_gateways -q` | Exit 0; **84 passed**, 3.547s. The emitted `hyperliquid_order_failed` line is an expected rejection fixture; suite result is OK. |
| IV-ADVERSARIAL | AC3 | `TMPDIR=/tmp/native-trailing-verifier-tmp PYTHONPATH=.:/tmp python3` runs a unittest suite selecting only `test_*` methods declared in `VerifierCases.__dict__` and `GatewayCases.__dict__` from `/tmp/native_trailing_verifier.py` | Exit 0; **7 independently authored scenarios passed**, 0.691s. Imported/inherited repository tests are excluded from this count. |
| IV-SMOKE | AC4 | `TMPDIR=/tmp/native-trailing-verifier-tmp PYTHONPATH=. /tmp/hl-trailing-venv/bin/python scripts/smoke_native_trailing.py` | Exit 0; actual CLI preview accepts native policy; SQLite paper supervisor has no order attempts; real SDK signature recovers the generated in-memory account; **0 network requests**, live exchange unverified. |
| IV-DIFF | Scope/content | `git diff --check`, actual diff/manual new-file and document review, SHA-256 comparison with `candidate.json` | Exit 0; candidate hashes match. |

Also inspected the implementation owner's `post-refactor.log`: 433 tests passed in 23.277s. This is builder evidence, not an independent rerun of all 433 tests. Initial reviewer run passed 77 tests before additional regressions were added; later broad verifier discovery passed 38 including imported/inherited cases and is not counted as 38 new scenarios.

### Seven additional adversarial scenarios

1. Start with acknowledged, active native trail; reduce position from 1 to 0.4 externally and restart. Verify PROTECTED, trailing coverage 0.4 and exactly one trail submission.
2. Mark the native trail FILLED while 0.4 exposure remains. Verify an exit for 0.4 and no replacement trail.
3. Return explicit native rejection. Verify residual exit instead of retrying a new native trail.
4. Return UNKNOWN without native ID, then observe flat. Verify INTERVENTION persists rather than falsely closing with an unresolved owned attempt.
5. Use the actual managed gateway. Accept acknowledged oid 43 and valid quote-distance readback, but reject wrong coin/oid/side/reduce-only flag, oversized quantity and percent-distance text.
6. Remove the native acknowledgement ID while a matching trail appears in frontend orders. Verify it is foreign, is not adopted, and no invented trailing cloid query occurs.
7. Add a second matching foreign trail beside the known owned one. Verify ownership reconciliation rejects the foreign order.

Repository cases additionally cover dry-run and invalid inputs, lot/allowlist/direction guards, opaque acknowledgements, strict condition parsing, partial entry fixed SL before native activation, restart, missing coverage, canceled trails and cancellation of both protective kinds when flat.

## Acceptance assessment

- **AC1:** documented availability is distinct from account/order readback; provider and native coverage are exposed without claiming live verification.
- **AC2:** dry-run default, strict values/eligibility/precision/direction checks, SDK-owned asset mapping/signing and conservative unknown response handling are present. Real SDK signing was exercised offline.
- **AC3:** persist-before-send, one native attempt, terminal-entry wait, separate fixed SL, strict native-ID ownership, no inference-based adoption, conservative unknown intervention, residual exits and flat cleanup hold in inspected code and executed scenarios.
- **AC4:** focused and independent adversarial verification and additional real-SDK/CLI/SQLite smoke pass. Operational/reference documentation explains policy differences, unknown-result handling and rollback. Diagram browser validation and task-level receipts remain the main agent's separate responsibility.

## Limits and operational assumptions

All exchange I/O is stubbed or replaced. Native response shapes, actual exchange activation/mark watermark, partial execution and cancellation are **not** verified live. Unknown acknowledgements intentionally require manual reconciliation and cannot be adopted or retransmitted automatically. The app source is observational evidence, not a promised public SDK contract. The supervisor validates only acknowledged order identities and fails closed on unfamiliar readback. The smoke proves local signing/preview/paper persistence; it does not simulate a live fill. Adversarial fixtures reside in `/tmp`; the durable scenario descriptions and results are retained here. No new generalizable task-observer observation was identified beyond the already logged protective-semantics principle; observation-store writes remain owned by the main agent.

## Reviewed document identities

- `README.md`: `e048c52358d00bc4846bc994bb36bbee1a7783a0f0c6947427680622b3cb84e6`
- `docs/trading-operations.md`: `874538c3b422085731038eba177e9445a10268658b632d2cb689f921ffb576f7`
- `docs/architecture.md`: `09e9055d5c04b4462a6e4ae7ef62c384111d1238f506c8b61a3476ed38cb3916`
- `.agents/skills/hyperliquid-api/SKILL.md`: `64a51be89f491258552d8fc5ec469787e3d10a439332b2ff2c0627e522eafee3`
- `.agents/skills/hyperliquid-api/references/exchange-endpoint.md`: `f07db9d5f8ef3ed0db3883c5085844345dd193baa42453e45b550b29a6b5f3a8`
- `intent/hyperliquid-native-trailing.md`: `eae5ff7f8fbd4885f284693aa7115c79282bc6576fe86cda46c1717e5987cd92`
- `specs/hyperliquid-native-trailing.md`: `4f8f3ec8010b80e29aa9238796a97060445eebaae3ef939c077917eed37971a8`
- `plans/hyperliquid-native-trailing.md`: `c2c8e9d4ecb27940519c613c6e28e482e612a8e37cd6ab7eec54004cadcdf546`
