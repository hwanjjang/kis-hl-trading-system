# Independent implementation verification — revision 4

Verdict: PASS. Proposed HOTL decision: PROCEED. No unresolved mandatory finding identified.

Task hyperliquid-native-trailing, independent-verification iteration 5/10. Candidate sha256:9e3170c7054d5f58c4bfdbc246efd63a619ad1390500d0c2f97cbdffbc383628; base 94e8e9d15c28f37d91d2b8c1f82e593aaeb7f0e5; current committed parent 2a2540f73c5cf0233c8dc2d8925779872573cb57. All 20 manifest file SHA-256 values and the aggregate identity independently matched before and after execution. No implementation edits were made.

## Actual identity and scope
Verifier: /root/native_handoff_verify, OpenAI Codex GPT-6 family according to host instructions; exact backend version and reasoning settings are not independently exposed. Fresh non-author context, separate from builder /root. This is same-provider independent implementation verification, not cross-provider PR review, published review, or merge authorization. No additional agents, network calls, funded credentials, live exchange operations, commits, pushes or publication were used.

Read repository AGENTS, canonical intent/spec/plan including the final concurrent-backup amendment, task-observer, Karpathy, Hyperliquid, trade-journal and SDLC verification/policy instructions, revision-4 investigation/build/self-verification/test plan/results. Inspected runtime/CLI/test/smoke changes and documentation/CI changes against the current parent, plus the cumulative native client/parser/capability changes against base. Canonical current amendments supersede earlier historical local-default and alternate-only wording.

## Executed evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Focused affected suites, isolated TMPDIR | 132 tests passed, exit 0 | independent-focused.txt |
| Actual venv manual handoff script, PYTHONPATH=. and isolated TMPDIR | Passed; includes existing SDK signature and native smoke plus actual CLI/SQLite/gateway/supervisor handoff, partial native/local fill race and restart cleanup; zero network | independent-smoke.txt |
| Verifier-authored additional cases | 12 tests passed, exit 0; multiple rejection variants in parameterized subtests | independent-cases.txt, independent-results.txt |
| Candidate integrity and whitespace | 20/20 hashes and aggregate match; git diff --check exit 0 | independent-inputs.json |

Commands: `TMPDIR=/tmp/hl-pr21-r4-verifier python3 -m unittest tests.test_manual_adoption tests.test_native_trailing tests.test_managed_execution tests.test_managed_gateways tests.test_hyperliquid_client tests.test_operations_cli tests.test_journal_history -q`; `PYTHONPATH=. TMPDIR=/tmp/hl-pr21-r4-verifier /tmp/hl-trailing-venv/bin/python scripts/smoke_manual_handoff.py`; `PYTHONPATH=. TMPDIR=/tmp/hl-pr21-r4-verifier python3 /tmp/hl-pr21-r4-verifier/test_independent.py`.

## Acceptance challenges

- AC1/AC2: new HL plans default native plus local backup; KIS and explicit local remain local. Stored absent-selector reads retain local and absent-backup native rows do not silently enable backup. Dry-run/live authority and eligibility are unchanged. Tests exercise dry-run with no exchange admission reads.
- AC3 admission: identified filled buy entry and native reduce-only Stop Market ownership, flat-origin ordered ledger, retention anchor, current quantity and VWAP, full SL size/risk floor, eligibility/current ATR and gross portfolio/correlation limits are verified before import. Additional probes reject wrong current size/average, foreign open order, another same-coin execution, incomplete entry ledger, conflicting execution ID, stale quote and risk-limit/ATR mismatch. Identical duplicate execution is deduplicated and admitted. Existing focused cases reject retention loss, reused IDs, legacy ownership and wrong SL evidence.
- AC3 concurrency/atomicity: injecting a separate SQLite cancel control immediately before complete_adoption causes optimistic-version import failure with zero imported attempts. The control remains persisted; next poll closes only the handoff. Existing transaction-trigger failure test proves no partial ownership after failed import. The adoption guard also prevents entry transmission if an unadmitted adoption is incorrectly marked ENTERING; explicit recovery returns it to ADOPTING. Admission has no exchange write; next reconciliation alone may create trailing protection.
- AC3 dual exits: actual smoke latches local exit with native waiting, retains native and fixed-SL orders while exposure remains, reconciles a native 0.4 reduction before sending a residual 0.6 IOC, then verifies terminal cleanup over restart. Focused tests cover native condition intervention and old-backup-field behavior. Additional probe verifies generic account inconsistency continues freezing local automation even after a later clean snapshot. Both use one durable exit intent/attempt ledger and reduce-only writes.
- AC3 provenance: imported stop retains web origin with an explicitly matched real scope; a positive control removing only imported=true yields agent attribution, demonstrating the guard rather than a missing scope match. Explicit local adoption never transmits native trailing or a new entry.
- AC4: source/CLI/operations docs describe actual handoff limits, local start-at-admission, single account/database requirement, simultaneous policies and rollback constraint. CI invokes the exact smoke exercised locally. Diagram source/HTML hashes and supplied design validation/browser/visual evidence are retained; this verifier did not rerun browser/visual rendering. Builder's 470-test full regression is reused for unchanged broader scope, not claimed as independently executed.

## Findings and limits

No product finding meeting the mandatory threshold was observed in the assigned bounded verification. Tests all passed on their first independent run. Real CLI, SQLite, SDK signature recovery, gateway and supervisor code were exercised with simulated exchange responses; live action acceptance, production account behavior, foreign UI races and distributed locking remain unverified. No Hermes runtime integration is claimed. Local POSIX lock and common SQLite path remain the operational boundary. Native unknown acknowledgements remain non-resubmittable; backup does not establish native order ownership.

Task-observer checkpoint: existing two active observation headers and principles read; no new generalizable observation accumulated. No shared observer files modified because this verifier owns only its delegated evidence paths.
