# Independent implementation verification — revision 3

Verdict: PASS. Proposed HOTL decision: PROCEED for the scoped PR update, subject to main-agent freshness and authorization checks. No unresolved mandatory findings. This is independent implementation verification, not a PR review or a cross-provider review.

## Identity and scope

Verifier context: /root/r3_verify, fresh delegated context, OpenAI Codex (GPT-6 family per host instructions; exact backend version and resolved effort are not exposed). Implementation author: /root, OpenAI Codex GPT-6. Same provider, separate non-author context. Shared workspace with implementation frozen; verifier changed only assigned evidence records and isolated tests under /tmp/hl-pr21-r3-verifier. No further delegation, implementation/test edits, commit, push, external publication, live order, credential access, or merge.

Stable task hyperliquid-native-trailing; independent-verification iteration 4/10. Base 94e8e9d15c28f37d91d2b8c1f82e593aaeb7f0e5; committed head 59400e9ee3b0c289da6176021a0efccc6bf6c08f; candidate sha256:a7fc3e2fad780c845d1ffd3faaac824f8b49e01f5aebaa055f1e2835973006f9. All ten candidate file SHA-256 hashes matched independently before and after tests. Aggregate identity recomputed from json.dumps({base, files}, sort_keys=True) matches. Consumed input hashes and all individual candidate hashes are retained in independent-inputs.txt. The artifact index was inspected for stage identity and canonical references; its historical endpoint field remains local, while current intent and assignment authorize the parent's existing PR update only. This report does not grant external authority.

Read AGENTS.md, canonical intent/spec/plan including the correction amendments, revision-3 test/build/self-verification/results, artifact index, task-observer, karpathy-guidelines, Hyperliquid skill, SDLC verification/host/subagent contracts and normative policy. Reviewed the exact HEAD-to-candidate runtime, regression and smoke changes, and corresponding operations/architecture/API reference changes. Runtime diff is narrowly limited to the dedicated parse exception, gateway diagnostic preservation, and supervisor marker transitions; client/instruments are unchanged from committed head.

## Actual checks

| Check | Actual execution and result |
| --- | --- |
| Affected regression | TMPDIR=/tmp/hl-pr21-r3-verifier python3 -m unittest tests.test_native_trailing tests.test_managed_execution tests.test_managed_gateways tests.test_hyperliquid_client tests.test_operations_cli -q — 115 tests, PASS, unittest exit 0; independent-focused.txt. |
| Separate functional smoke | PYTHONPATH=. TMPDIR=/tmp/hl-pr21-r3-verifier /tmp/hl-trailing-venv/bin/python scripts/smoke_native_trailing.py — PASS, exit 0; actual CLI, SQLite, real SDK signer recovery, and four lifecycle replays; independent-smoke.txt. |
| Independently authored integrated challenges | PYTHONPATH=. TMPDIR=/tmp/hl-pr21-r3-verifier /tmp/hl-trailing-venv/bin/python /tmp/hl-pr21-r3-verifier/test_independent.py — 9 tests PASS, unittest exit 0; independent-integrated-final.txt. Test source preserved in independent-tests.txt. |
| Whitespace and candidate integrity | git diff --check — exit 0. All 10 file hashes and aggregate candidate digest match. |

Independent tests use the actual ReplayExchange boundary, ManagedHyperliquidGateway, Supervisor and ExecutionStore/SQLite. Each step reconstructs supervisor/store to challenge restart persistence. Exchange calls are simulated; no funded account or real exchange transmission occurs. Cancellation fixture acknowledges without changing status, proving cleanup requires later terminal readback.

## Acceptance evidence

- AC1/AC2: affected suites and separate real-SDK signature/CLI paper smoke pass. No client, eligibility, default-mode or instrument change exists in this correction. Documentation preserves the distinction between native capability, verified readback and unverified live execution.
- AC3 parser isolation: prior active coverage becomes zero after malformed best data; fixed-SL coverage remains one. Persistent malformed data beyond grace does not exit solely due to the parser and never resubmits a trailing order. Explicit exit still sends exactly one reduce-only IOC and preserves both existing protections until flat.
- AC3 strict boundaries: 12 direct gateway mutation cases reject wrong coin, oid, side, reduceOnly, trigger/type, oversized/negative/nonfinite quantity, percentage distance, mismatched quote distance and explicit activation. Malformed trailing condition cannot swallow these errors. Integrated inconsistent exposure clears the native marker, and later valid readback plus explicit exit does not reopen automatic actions.
- AC3 same-ID recovery: malformed condition -> valid waiting -> active moves INTERVENTION -> PROTECTING -> PROTECTED with the same known oid, coverage one, and exactly one trailing transmission across restarts.
- AC3 terminal/cleanup: six terminal status shapes normalize correctly despite malformed condition; marginCanceled on the acknowledged trail immediately sends residual exit. Independently reconciled flat exposure cancels fixed SL and trailing once, remains CLEANUP after mere cancellation acknowledgement, then becomes CLOSED after both terminal readbacks.
- AC3 generic containment/transport: a transient OSError preserves the native-only marker; on recovery, canceled fixed SL after grace sends the required exit. Exit deadline exhaustion clears the exception permanently; later valid readback cannot send another exit.
- AC4: the assigned affected suite, additional runtime smoke, independent integrated challenge, exact-candidate hashes, and docs checks passed. Builder's separate 458-test full-suite run is retained and was not independently rerun; the unchanged broader scope justifies that reuse.

## Findings and limitations

No product finding meeting the mandatory-finding threshold was observed. The initial independent run had one verifier-test assertion failure: it expected exit deadline exhaustion at 40 seconds although the fixture specifies 60 seconds. The oracle was corrected to derive the configured deadline plus elapsed start offset; no product code was changed. Initial output remains in independent-integrated.txt; final rerun contains nine passing tests. This was a fixture expectation correction within this verification attempt, not a new implementation candidate.

Live exchange acceptance, undocumented condition formats not represented by fixtures, network behavior and funded-account execution remain unverified. The replay imports the existing exchange boundary but the added scenario sequences and expected outcomes were independently authored against the canonical spec. This same-provider fresh-context verification cannot satisfy an eligible cross-provider PR review; no such claim is made. Main owns any subsequent commit/push/CI and endpoint assessment.

Observation checkpoint: existing observer metadata/principles were read. No new reusable observation beyond the existing test-oracle principle was identified; no out-of-scope observation-log writes were performed.
