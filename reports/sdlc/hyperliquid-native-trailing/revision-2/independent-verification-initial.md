# Independent verification — revision 2, initial corrective candidate

## Verdict

**CHANGES_REQUIRED**

The candidate fixes the originally reported no-oid/rejected-submission, waiting-order, distance-precision, and parser-separation cases covered by the focused suite, but it conflates a never-established rejected submission with a previously established native trail whose known order later becomes rejected. That violates the established-terminal residual-exit requirement.

## Candidate identity and freshness

- Implementation author: `/root` (OpenAI GPT-6).
- Independent verifier: `/root/correction_verify`, fresh verifier context; this report is independent implementation verification, not the cross-provider PR review.
- Base main: `94e8e9d15c28f37d91d2b8c1f82e593aaeb7f0e5`.
- Starting PR HEAD: `f99c8a5ae51f84c63f898c81225321bc0ddcc046`.
- Candidate manifest: `revision-2/candidate.json` with candidate identity `sha256:c0d6ed5976b9b61f90ad87e20c4ed8a4ec3472364bd41018e550bc46acb4d9c5`.
- Candidate manifest file SHA-256: `a4f16975e53c7406ef14a9ca706ca6b472c493e2257176d7f845f009cfd930ba`.
- Freshness check: every candidate file was hashed during this verification and matched the manifest exactly:

| File | SHA-256 |
| --- | --- |
| `kis_hl/hyperliquid/client.py` | `f3440c0499f5de3af08c0572dfaa5550e9e98b04d872a7f67ed97a8b5dec20d3` |
| `kis_hl/hyperliquid/trailing.py` | `3f22640f833271fa483e9214174d46ced38dea8d2e7f570c524a848294f4f2dd` |
| `kis_hl/instruments.py` | `5f45ee75dfcb1e89ed785e9260484ce76fed37070784e88d443ad13e4433564c` |
| `kis_hl/managed_gateways.py` | `72d1a7459437c4a89842d8049c338dba91f1fbe42ad79fadeab33b870267dd59` |
| `kis_hl/managed_execution.py` | `c20bfb5135b5d688541185ed638a0b20e50902cce3b3970d700aa9b35c549b70` |
| `tests/test_native_trailing.py` | `44703cc9df95902496bad2eccd3e164da9da457ba08f0dc7e358e4594072d90e` |
| `scripts/smoke_native_trailing.py` | `1d6ad7bfad5aadb6af5233d307b493acc3eb55f1633a69c1df92a72b6a623adf` |
| `docs/trading-operations.md` | `787e0a8c85dba3af37b73b05a470798bb133d3341a4ac55b0bc2b326e2753b2b` |
| `docs/architecture.md` | `22352393cdc21548652507d8f86735b6ac888cb49be408a67ffcf48f14c80c42` |
| `.agents/skills/hyperliquid-api/references/exchange-endpoint.md` | `ef2657e7110d0d40b0c00fcf216abb322c15465820733fb359c8c2171f263cef` |

## Must Fix finding

### HIGH | Bug / Spec | `kis_hl/managed_execution.py:578`, `kis_hl/managed_execution.py:722`

**Finding:** A known-ID native trailing order that was previously verified active can later receive terminal `rejected` status, but the supervisor treats it as the never-established submission-rejection case and does not request residual exit.

**Evidence:** Snapshot reconciliation first promotes any terminal readback, including `rejected`, onto the durable attempt at lines 578–579. Native trailing handling then tests `not order_id or status == REJECTED` at lines 722–725 before the generic terminal branch at lines 726–728. Therefore a trail with a known order ID and prior active readback enters `INTERVENTION` with `native_trailing_intervention=true`; `exit_requested_ms` is not latched. Independent inspection confirms the control-flow defect. The builder separately reproduced the concrete transition `PROTECTED` at `t=5` followed by known-ID order status `rejected` at `t=6`, resulting in `INTERVENTION` and no exit; that reproduction is corroborating evidence and was not counted as an independently executed verifier test.

**Impact:** The position remains under the fixed stop and manual intervention, but the required residual-exit policy for termination of an established native trail is skipped. This is an explicit AC3/corrective-contract violation in a live-risk state transition.

**Reproduction/verification:** Establish a native attempt with an acknowledged order ID, return a matching active readback so the row reaches `PROTECTED`, then return `rejected` for that same order ID. Assert that an exit is requested/sent and that the submission-rejection exception is not selected. The current candidate instead remains `INTERVENTION` without exit.

**Related requirement/policy:** Corrective AC3 distinguishes never-accepted rejection from termination of an established trail; the specification requires a previously established terminal trail to retain residual-exit behavior and forbids resetting its watermark.

**Confidence:** High.

**Disposition:** Must Fix. Track whether the known order was established by verified active readback, and reserve the rejection/no-oid intervention exception for a submission that never established trailing protection. Add a regression covering active known-ID → rejected terminal transition.

## Checks performed

| Check | Command or method | Result |
| --- | --- | --- |
| Focused native trailing tests | `TMPDIR=/tmp/hl-pr21-verifier /tmp/hl-trailing-venv/bin/python -m unittest tests.test_native_trailing -q` | **PASS**, 32 tests in 2.901 s |
| Candidate file identity | `sha256sum` over all ten manifest files | **PASS**, all hashes matched `revision-2/candidate.json` |
| Candidate/base identity | `git rev-parse HEAD` and explicit base resolution | **PASS**, HEAD `f99c8a5...`, base `94e8e9d...` |
| Intent/spec/plan alignment | Independent read of canonical artifacts and revision-2 triage, investigation, test plan, and design | **FAIL** for the known-ID terminal-rejection branch above; no other blocking discrepancy identified in the bounded inspection |
| Precision implementation | Independent inspection of `price_increment`, pre-entry persistence, raw metadata decimal tick, and client validation | **PASS by inspection** for the corrected scope: distance precision is based on the distance itself and raw perpetual decimal precision, while the pre-existing quote grid remains used for fixed-SL/exit price rounding |
| Parser versus managed semantics | Independent inspection of parser and `trailing_readback` | **PASS by inspection**: known percent/activation syntax parses, while managed quote-distance/immediate-activation mismatches fail closed |

## Limitations and not-run checks

- No live Hyperliquid order, activation, readback, cancel, or network request was performed. Exchange acceptance and exact live response behavior remain unverified.
- The builder's 104-test focused run, 447-test full regression, and integrated SDK/SQLite smoke were reviewed as upstream evidence but were not independently rerun in this bounded initial verifier pass.
- An independently authored adversarial script was drafted under `/tmp/hl-pr21-verifier/`, but execution was stopped when the blocking known-ID terminal-rejection defect was confirmed. Its additional unknown/rejected restart, fixed-SL disappearance, explicit-exit, generic-intervention, waiting/restart, parser, old-row, and precision-extreme cases are **not-run** and make no contribution to this verdict.
- The correction must receive renewed candidate hashes and fresh independent verification; this report applies only to `sha256:c0d6ed5976b9b61f90ad87e20c4ed8a4ec3472364bd41018e550bc46acb4d9c5`.
