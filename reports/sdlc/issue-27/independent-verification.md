# Issue 27 independent verification

Verifier: delegated `/root/verify_issue27` context, separate from implementation.
Date: 2026-09-24. Endpoint: local only. Final verdict: **PASS** for AC1–AC5 on the
corrected candidate identified below. No unresolved Must Fix findings remain.
This is independent acceptance verification,
not a PR review or a cross-provider review. Main owns stage iteration accounting.
No product files, shared planning/state, credentials, live account state, GitHub
messages, or signed venue operations were modified by this verifier.

Upstream contract: `intent/issue-27.md`, `specs/issue-27.md`, `plans/issue-27.md`.
Base HEAD: `adb71fa5b1713164ab4aff1d5916d26c47f96950`.

## Initial examination: CHANGES_REQUIRED

The initial candidate implements durable one-attempt add ownership and account-total
sizing, but independent boundary probes found two implementation defects. The author
was notified promptly. Final correction verification is recorded below when complete.

| ID | Severity/category | Location | Finding and impact | Evidence / reproduction | Requirement | Confidence | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| IV-1 | HIGH / authorization bounds | `kis_hl/conditional_add.py:validate_add`, `kis_hl/managed_gateways.py:submit`, supervisor protection | An add plan could authorize stricter quote age, protection grace, and retry bounds than its owner, while execution silently used the owner's looser bounds. | In the existing add fixture, authorize `max_quote_age_ms=100`, `protection_grace_ms=1`, `max_exit_attempts=1`. Admission and transmission succeed. Feed the resulting add attempt to the actual managed gateway with a Mock trading client: signed expiry is `1789948840000`, versus authorized quote deadline `1789948800110`; supervisor still uses grace 5000 and 3 attempts. | AC2 bounded authority; AC3 bounded protection | High | Resolved and independently verified: owner-parameter equality rejects changed shared bounds; final 184-test suite passes. |
| IV-2 | HIGH / fill lifecycle | `kis_hl/managed_execution.py` add protection grace and `needs_overlay` | Detection of add fills compared aggregate fills with the original *requested* entry quantity. A partially filled, canceled original entry could therefore receive an authorized add and immediately liquidate instead of protecting it. Native overlay eligibility had the same incorrect predicate. | Create entry quantity 2, fill 1, cancel its residual, reconcile to PROTECTED. Approve/add 0.5 after three days. Before add: actual entry fill 1, original quantity 2. First post-add reconciliation produces `EXIT_PENDING`, covered size 1, and exit quantity 1.5, with no incremental SL/native overlay. Orders: entry 2, SL 1, trail 1, add .5, exit 1.5. | AC3 actual combined exposure, partial-fill lifecycle | High | Resolved and independently verified: actual add fills determine grace/overlay; original independent transition now reaches full protection. |
| IV-3 | MEDIUM / required checks | `tests/test_strategy_signals.py:test_hold_or_add_decision_cannot_be_used_as_a_new_entry` | Existing changed-scope regression fails because the new rejection message lacks the asserted word `entry`. The add is correctly rejected; this is test/message compatibility, not an authorization bypass. | First 132-test command below: one failure in the add subcase. | AC5 changed-scope tests | High | Resolved and independently verified: rejection still occurs and the final changed-scope suite passes. |
| IV-4 | HIGH / authority expiry | `kis_hl/strategy_signals.py:check_authority`, `kis_hl/managed_execution.py:_try_add` | Signal/grant expiry was checked only before submission; a longer plan expiry could keep an unfilled add live after the source authority expired. This also contradicted the documented minimum-expiry contract. | In the add fixture, ingest a distinct signal with expiry `NOW+20`, authorize a plan expiring `NOW+40000` at `NOW+5`, step at `NOW+10`, and again at `NOW+21`. The add remains `open` with attempt expiry `NOW+40000` and owner `PROTECTED`. | AC2 bounded expiry; AC5 documented contract | High | Resolved and independently verified: plans outlasting signal or grant authority are rejected before enqueue; final suite and original expiry probe pass. |

IV-2 reproducible procedure uses only `tests.test_conditional_add.AddGateway`,
`ExecutionStore` with a temporary SQLite file, and `Supervisor`. Clone `protected()`
with initial `quantity="2"`, call `gateway.fill(entry, "1", terminal=False)`, set the
entry order status to `canceled`, reconcile four ticks, then use the existing
`add_signal()`/`add_plan()` and fill the approved add with `0.5`. Inspect the next
tick's stored state and `gateway.sent`. No live transport is used.

## Executed checks

1. `python3 -m unittest tests.test_conditional_add tests.test_managed_execution tests.test_managed_gateways tests.test_strategy_signals tests.test_strategy_tools tests.test_native_trailing tests.test_manual_adoption -q`
   — 132 tests in 21.666s, 131 passed, one failure (IV-3), exit 1.
2. `python3 -m unittest tests.test_hyperliquid_client tests.test_operations_cli tests.test_risk -q`
   — 45 tests, one environment error: system Python lacks the Hyperliquid SDK.
3. `/tmp/hl-trailing-venv/bin/python -m unittest tests.test_hyperliquid_client tests.test_operations_cli tests.test_risk -q`
   — same 45 tests, all passed in 1.542s, exit 0. Existing SDK environment resolves
   the prior setup error; no dependency installation was performed.
4. Independent in-memory/temporary SQLite probes reproduced IV-1 and IV-2 above.
5. After IV-1 correction, setting only `max_quote_age_ms=100` in the existing add
   fixture raises `ValueError: Add must preserve frozen ATR and independent protection parameters`.
6. After IV-1/IV-2/IV-3 corrections, all ten modules from commands 1 and 3 were
   executed together with `/tmp/hl-trailing-venv/bin/python`: 182 tests passed in
   21.619s. The original IV-2 probe, using a real initial quantity-2 attempt filled
   only to 1 and canceled before the add, now reaches PROTECTED with SL/native TS
   coverage 1.5 and no exit order. These three findings are verified resolved.
7. `/tmp/hl-trailing-venv/bin/python scripts/smoke_conditional_add.py` passed:
   balance 1000, capital 10000, one add attempt, tranche fill .5, remaining/SL/native
   TS 1.5, PROTECTED. Network creation is forbidden in the smoke. Each CLI handler
   reopens temporary SQLite. An earlier overlapping invocation was blocked by the
   fixture account lock; the reported successful run was serial after unit tests.
8. After the subsequent independent `activeAssetData` buying-power enhancement,
   `/tmp/hl-trailing-venv/bin/python -m unittest tests.test_managed_gateways tests.test_hyperliquid_client -q`
   passed 46 tests in 0.998s. Gateway/client source was reread. Unchanged supervisor
   lifecycle evidence from the 182-test run is reusable for this isolated change.
9. `git diff --check` passed after the first corrective test run. A later focused
   expiry probe discovered IV-4; the previous green suite did not cover that case.

The initial tests establish account total 1000 / capital 10000 / one-unit risk 100,
duplicate/unknown collateral rejection, manual authority and completed-bar gates,
SQLite reopen replay and unknown-outcome suppression, incremental stop coverage,
native overlay preservation, bounded protection failures, full residual exits after
competing fills, scoped cleanup, and zero-mutation external-trail adoption rejection.
They do not replace the failed boundary probes.

The official [account abstraction modes documentation](https://hyperliquid.gitbook.io/hyperliquid-docs/trading/account-abstraction-modes)
was independently read. It describes unified balances in spot clearinghouse state
and says individual perpetual DEX user states are not meaningful for those balances.
The supported USDC-only unified-account reconciliation is consistent with that narrow
documented contract; other modes and nonzero unvalued assets remain blocked.

## Initial candidate file identities

SHA-256 recorded during the first examination, before final author corrections:

```text
2f099805d71f19a94a3f8ac573c146d4673c83a4693d4d8589df71beb56a3ee2  kis_hl/account_capital.py
296898bb4b46587aaaeb818c6035c131a7b46b0641e49ebc8bc9c9e62ca276e2  kis_hl/conditional_add.py
d0ddd69345b2ae4749e4a500306f78167980c8070c00ad9f5ba043bbf5b585ea  kis_hl/managed_execution.py
f63d9945b693bd9c331be2093202543e96b6997884d5fa31931f59dc0d667614  kis_hl/managed_gateways.py
c2731a6bf1f0ac7991e81ba17416b9adfdbfad535f7a6ff6c151e26cc420018b  kis_hl/strategy_signals.py
537a4b8a02d816127df5429a7d1ee5da1a16300693f9001b31e08adf67b1167b  kis_hl/strategy_tools.py
a862115232ccce91aa3d0b34e4092baf2f0d05fd28f74f4d1bbfd17430fef7f3  kis_hl/manual_adoption.py
11e6014fd91aaa3c283d8b720a471ba198d5792d55662a365611a3e22cfcba91  kis_hl/hyperliquid/client.py
196bb2b14b4b3517b385c17e03b2c1d056060e40b06e4436091bf1a1d7103614  tests/test_conditional_add.py
e77d8bc358265cb156a17d74dfef38a8f3d791ff12c8a4bf88aa499c1d228593  tests/test_strategy_tools.py
```

## Scope and remaining evidence

All execution tests use stub transports/gateways and temporary databases. No live
orders, readbacks, account identifiers, or credentials were used. Actual exchange
native-trail activation, simultaneous reduce-only order handling and collateral
readback behavior remain unverified. AC5 CLI/SQLite smoke and owner-document review
are pending author completion. Fresh candidate digests, correction reruns and final
AC verdict must supersede this initial receipt before a PASS claim.


## Final corrective verification: PASS

Final execution at approximately 2026-09-24 16:38 UTC:

```bash
/tmp/hl-trailing-venv/bin/python -m unittest tests.test_conditional_add tests.test_managed_execution tests.test_managed_gateways tests.test_strategy_signals tests.test_strategy_tools tests.test_native_trailing tests.test_manual_adoption tests.test_hyperliquid_client tests.test_operations_cli tests.test_risk -q
/tmp/hl-trailing-venv/bin/python scripts/smoke_conditional_add.py
git diff --check
```

The test command passed **184 tests in 20.462s**, exit 0. The smoke command passed,
exit 0, with network forbidden, temporary SQLite reopened by CLI handlers, one add
attempt, .5 filled add, 1.5 remaining exposure, 1.5 verified fixed SL coverage, 1.5
verified native TS coverage, and final state PROTECTED. Diff whitespace validation
passed, exit 0. Mock-client order logs in unit output are fixture events, not live
signed requests.

The original short-signal probe was rerun independently after IV-4 correction:
`expires_ms=NOW+20` on the signal and `NOW+40000` on the plan now raises
`Add plan expiry exceeds signal authority` at authorization, with no add attempt.
The added grant regressions also reject a plan outlasting its grant, reject ordinary
entry-only grants, and reject a revoked grant before submission.

| Criterion | Outcome | Independently checked evidence |
| --- | --- | --- |
| AC1 | PASS | Capital regression 1000 → 10000 → 100; segment value 123 ignored; unknown/overlapping collateral and mismatched scope reject. Actual gateway collects account-total evidence and separate active-asset buying power; client methods bind effective account/instrument. |
| AC2 | PASS | Table-driven confirmation/authority/exposure/bounds rejection; immutable signal/tranche reservation; persisted UNKNOWN attempt never resent; same approved signal after SQLite reopen submits once; signal/grant expiry and revoke regression. |
| AC3 | PASS | Stub gateway partial add then completion; actual tranche fills retained; incremental SL and full-size native overlay; old native watermark preserved; initial partial-entry/cancel edge independently reproduced and fixed; failed SL/overlay enters bounded recovery/intervention retaining verified stops. |
| AC4 | PASS | Existing external percentage TS returns migration-required with no signed mutations; protective partial fill plus competing local/native fills produces full residual exit quantities 1.3 then .5, never a half-profit exit; cleanup leaves unrelated orders untouched. Actual gateway exit path remains reduce-only. |
| AC5 | PASS | CLI main/SQLite smoke, changed-scope tests and whitespace checks pass. Reviewed owner docs for capital, add authority, full exit, current unsupported modes and live uncertainty. Earlier ETH discussion explicitly remains unarmed. |

Reviewed owner documentation: `docs/trading-operations.md`,
`docs/strategy-tools.md`, `docs/strategy_execution_design.md`, `docs/architecture.md`
and README usage. The misleading entry-only setup wording was corrected to apply
explicitly to `enter`; add points to its pullback/rebreakout contract. The diagram
source/HTML exists; author-owned browser/visual validation is separate from this
verifier's offline execution acceptance, and this report makes no independent
browser-rendering claim.

Supported behavior remains deliberately narrow: USDC-only unified-account totals,
existing local owner/protection settings, explicit one-signal add authority, and
full residual exits. Unsupported capital modes and external/native-only migration
remain fail-closed. No scheduler, discretionary half exits, live activation, live
account access, order placement, publication, or merge was performed in this
verification. Offline PASS does not establish exchange behavior.

### Final candidate SHA-256 identities

These identify the files read/executed in the final local checks. Later changes to
these files require impact assessment and renewed affected evidence.

```text
e00f96692030d08b586e06ce55c0b5f8334bc6cca21be40ff23957bad98be2ed  intent/issue-27.md
60a6ba7d7345a591a36bcdddc388e10b4951e47178f57f7e6ea199efe82b2ba9  specs/issue-27.md
50c11a49823556499e635a215da0441e3591cb32d047c9d0bf990a3b674520cd  plans/issue-27.md
12528b425e597752de2443e345d233ef0047c45cbbe38a5bba1912d854d2a133  kis_hl/account_capital.py
53c5009a9cbda40342bd493eb9347f5ac67d79d8e7a116905b729d113ddb09dd  kis_hl/conditional_add.py
244ce09db6e2acfa55056cf7afd8e2beffe1433d5c6eabc78b0864de39646720  kis_hl/hyperliquid/client.py
98c2ab68e4d2d310431ab968f7a47bc89771880bb785c37443a666f7b78acf61  kis_hl/managed_execution.py
b9622f57889c0635cb1b665611b0d65793c28ce1d8ea6373a1137026ceff6f3d  kis_hl/managed_gateways.py
a862115232ccce91aa3d0b34e4092baf2f0d05fd28f74f4d1bbfd17430fef7f3  kis_hl/manual_adoption.py
6c870b2411a2f9388196ab5d67e225132c968f1d11642d5c8384644f9577a09f  kis_hl/operations_cli.py
d993a8b8dc90e4011ef560407bf24bc14474a3db112c2d1153a59af2be9b4c5d  kis_hl/strategy_signals.py
537a4b8a02d816127df5429a7d1ee5da1a16300693f9001b31e08adf67b1167b  kis_hl/strategy_tools.py
451c5705bf0dfdbcd2b8c8bfa5014d61ac545b5b90de9e76668d755b7971fd6f  scripts/smoke_conditional_add.py
b070a20cfaed680843cb7e0406f6257064668a38a0743df3227a17506f46ce46  tests/test_conditional_add.py
473dbc7e6e65334a9289a9103888d3d1cc3fe55b744e1776afa8e11955493aaa  tests/test_managed_execution.py
4a0c15dca18297412d016db3ed149f336218ee380f4ff286ff7e44a0aae19c21  tests/test_managed_gateways.py
bd36715d55013010e1b31bcdb81963601e5316947af504e47523d6a79cfeb077  tests/test_strategy_signals.py
e77d8bc358265cb156a17d74dfef38a8f3d791ff12c8a4bf88aa499c1d228593  tests/test_strategy_tools.py
2ebecd2f1ec1c41b2c3cf1253631202fdf0366042f891d45f8f08311eba8dd05  tests/test_native_trailing.py
abed2c83f3e36ad7dd073c230a2a80ff09e3f63521661380aadc2c6275b94d7f  tests/test_manual_adoption.py
145d0e95b26a546755ff3cfcbdaa64e46ac70acd4420e70110f70f2ba0e9b07b  tests/test_hyperliquid_client.py
d1dfe60e03b67d880ba0a25280d008c63375eb6c876779cf6d3689cc89acc671  tests/test_operations_cli.py
040cebc2e5de19c1e186fb5b5cdfbd6ae2cff682e6530805078e94f6615a7bc1  tests/test_risk.py
7cb435440ace433c5247d0331439d650e56ae1da272e6df71494365687810b48  README.md
9312ddd90c08836e77adfeb80d49f3d0b3b6277d39b6adb516f589f1a7166ef9  docs/trading-operations.md
feb6520e8b9e0b2a93db040122b1d478fe54deec3a8b615804b7e3044362e88d  docs/strategy-tools.md
41d5f7bf508f2b30ea83e7c2327235572ba6ff663fe8742323a81a7938261570  docs/strategy_execution_design.md
311bfef4d203868630d4d01353a80ebcfd556836c3d4e5654a4cc7b32daa4a62  docs/architecture.md
```
