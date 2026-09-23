# Independent verification — revision 2 final candidate

## Verdict

**PASS**

No unresolved mandatory finding was identified in the frozen candidate. The initial known-ID terminal-rejection finding is corrected: only a trailing attempt without an acknowledged order ID receives the submission-intervention exception; any acknowledged attempt that later becomes terminal follows the residual-exit path. The focused suite, six independently authored lifecycle boundary checks, and the offline SDK/SQLite functional smoke all passed on the exact candidate.

This report is independent implementation verification. It is not the required different-provider PR review.

## Candidate identity and freshness

- Implementation author: `/root` (OpenAI GPT-6).
- Independent verifier: `/root/correction_verify`, fresh verifier context.
- Base main: `94e8e9d15c28f37d91d2b8c1f82e593aaeb7f0e5`.
- Starting PR HEAD: `f99c8a5ae51f84c63f898c81225321bc0ddcc046`.
- Frozen candidate: `sha256:e5ac77a4207f4964f7146a84838d74182b276b1afed0211a4b7779c0959391a9` from `revision-2/candidate.json`.
- Candidate manifest file SHA-256: `aab0fba2ffbe2cfab72443868791e1dfb07d70cc5e8580368eb090b30c7f7c51`.
- The final recheck confirmed the runtime, regression test, smoke, and manifest hashes remained unchanged after independent execution.

| Candidate file | Verified SHA-256 |
| --- | --- |
| `kis_hl/hyperliquid/client.py` | `f3440c0499f5de3af08c0572dfaa5550e9e98b04d872a7f67ed97a8b5dec20d3` |
| `kis_hl/hyperliquid/trailing.py` | `3f22640f833271fa483e9214174d46ced38dea8d2e7f570c524a848294f4f2dd` |
| `kis_hl/instruments.py` | `5f45ee75dfcb1e89ed785e9260484ce76fed37070784e88d443ad13e4433564c` |
| `kis_hl/managed_gateways.py` | `72d1a7459437c4a89842d8049c338dba91f1fbe42ad79fadeab33b870267dd59` |
| `kis_hl/managed_execution.py` | `850736dc8e47d233d03362200bb3c09f2f4e554a9ebf4090215db17153725df1` |
| `tests/test_native_trailing.py` | `9cdd5d4dbb971633e151ecd902af0f9edf76f272fc384ede61d5f98265853511` |
| `scripts/smoke_native_trailing.py` | `1d6ad7bfad5aadb6af5233d307b493acc3eb55f1633a69c1df92a72b6a623adf` |
| `docs/trading-operations.md` | `787e0a8c85dba3af37b73b05a470798bb133d3341a4ac55b0bc2b326e2753b2b` |
| `docs/architecture.md` | `22352393cdc21548652507d8f86735b6ac888cb49be408a67ffcf48f14c80c42` |
| `.agents/skills/hyperliquid-api/references/exchange-endpoint.md` | `ef2657e7110d0d40b0c00fcf216abb322c15465820733fb359c8c2171f263cef` |

## Findings

No BLOCKER, HIGH, MEDIUM, LOW, or policy-level Must Fix finding remains.

The prior report for candidate `c0d6ed...` is preserved as `independent-verification-initial.md`. Its HIGH finding is resolved in this candidate. At `kis_hl/managed_execution.py:722`, submission intervention is now restricted to missing `order_id`; at line 726, a known-ID `rejected`, `canceled`, `filled`, or `expired` attempt reaches the terminal branch and latches `exit_requested_ms`. The new regression demonstrates active known-ID → rejected → exit without sending another trailing order.

## Independent checks and results

| Check | Command or method | Result |
| --- | --- | --- |
| Candidate identity | `sha256sum` over all ten manifest files, plus final rehash of runtime/test/smoke/manifest | **PASS**, all hashes matched candidate `e5ac77...` |
| Focused affected suites | `TMPDIR=/tmp/hl-pr21-verifier /tmp/hl-trailing-venv/bin/python -m unittest tests.test_native_trailing tests.test_managed_execution tests.test_managed_gateways tests.test_hyperliquid_client tests.test_operations_cli -q` | **PASS**, 105 tests in 8.594 s |
| Adversarial lifecycle boundaries | `PYTHONPATH=. TMPDIR=/tmp/hl-pr21-verifier/adversarial /tmp/hl-trailing-venv/bin/python /tmp/hl-pr21-verifier/adversarial_verify.py ... -v` | **PASS**, 6 tests in 1.524 s |
| Offline functional smoke | `PYTHONPATH=. TMPDIR=/tmp/hl-pr21-verifier/smoke /tmp/hl-trailing-venv/bin/python scripts/smoke_native_trailing.py` | **PASS**, real SDK signature recovery, SQLite, real gateway/supervisor integration, simulated exchange boundary, zero network requests |
| Diff hygiene | `git diff --check` | **PASS** |

The six adversarial cases independently exercised:

1. rejected and unknown no-ID attempts across restart retain the fixed SL, do not retry, and do not exit solely because trailing submission failed;
2. an explicit exit request remains executable during native submission intervention;
3. a temporary `RuntimeError` read outage preserves the specific native-intervention marker and resumes fixed-SL monitoring after recovery;
4. foreign ownership clears the native exception and retains generic intervention freeze;
5. a malformed snapshot clears the native exception and retains generic intervention freeze; and
6. a previously active known-ID trailing order that becomes `rejected` exits residual exposure and does not recreate the trail.

The functional smoke additionally observed:

- CLI preview and SQLite paper execution produced no order attempts;
- SDK signature recovery succeeded;
- real gateway/supervisor waiting → restart → active behavior succeeded;
- rejected submission retained its fixed stop;
- fixed-stop loss initiated exit;
- distance `4` was persisted before entry at quote `100000`, `szDecimals=5`, and ATR `2`; and
- `network_requests` remained `0`.

The first adversarial invocation omitted `PYTHONPATH=.` and failed during import with `ModuleNotFoundError`; it was an environment setup failure before test discovery. The corrected command above executed the six scenarios successfully.

## Requirement assessment

- **Rejection/unknown:** PASS. Missing-ID rejection or unknown outcome becomes specific intervention without retry, resemblance adoption, or rejection-only exit. Fixed-SL monitoring, explicit exit, and cleanup remain reachable.
- **Established terminal trail:** PASS. Acknowledged terminal attempts, including a later `rejected` status, latch residual exit and cannot reset the exchange watermark.
- **Waiting:** PASS. Full-sized verified open waiting orders retain zero active trailing coverage, remain `PROTECTING` across grace/restart, and do not trigger a waiting-only exit. Active matching readback moves to `PROTECTED`.
- **Precision:** PASS. Native quote retracement uses the raw perpetual decimal tick plus the distance's own five-significant-figure rule, persists before entry, and rejects normalization to zero before exposure. Integer distances retain the documented integer exception.
- **Parser/readback:** PASS. Known quote/percent, optional activation, best waiting/omitted, and active best syntax parse separately; managed verification still rejects percent, explicit activation, malformed, duplicate, unknown, nonfinite, and mismatched clauses.
- **Old in-flight records:** PASS. A record without `native_trailing_distance` normalizes from current metadata before its first trailing send and does not resend an existing attempt.

## Scope note and limitations

The gateway's existing `price_step` remains `max(decimal_tick, quote-derived significant-figure grid)` for fixed-SL trigger/execution and bounded exit prices. This is separate from the correction: native retracement now uses `trailing_price_step`, the raw metadata decimal tick, and applies significant figures to the distance itself. No regression in the pre-existing fixed-SL/exit rounding path was observed, and it is not reported as a finding for this correction.

The verifier did not place a live order or perform a network request. Actual Hyperliquid acceptance, activation timing, readback strings, and cancel behavior remain explicitly unverified live. The main agent's 448-test full regression was reviewed as upstream evidence but was not independently rerun; the independently executed 105-test affected suite and integrated functional smoke passed on the exact frozen candidate.
