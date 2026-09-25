# Third review correction verification

Source candidate: `0247846f212180b236cf803371254661bbcd6490ba95d58b45146be66d3d8f47`; base `cb0baa6ab0eb7c73910387ee2fe6eec2863ebcb5`. All27 source hashes in
round3-candidate.json match the verified bytes. This report is local verification,
not live exchange validation, a cross-provider PR review or merge authorization.

- Initial regression Red:31tests,10 expected assertions plus1 fixture-expiry error.
  Fixture errors are not counted as product evidence; corrected status regression
  against the base cmd_supervisor yields the expected missing pending_adds KeyError.
- Focused Green:37tests PASS (18.675s), round3-green.log.
- Final scope:210tests PASS (31.463s), round3-scope.log.
- Additional smoke after the scope run:PASS, round3-smoke.log. Actual CLI handlers,
  temporary SQLite reopened on each invocation, stub exchange, sockets forbidden.
  Accepted add with lost acknowledgement appears UNKNOWN in both run --once and
  status while the existing position is PROTECTED. Partial readback reports
  SUBMITTED/filled0.2; terminal readback clears pending_adds. One send, combined
  exposure/verified SL/native TS1.5, final PROTECTED. Tranche history is retained.
- `git diff --check`:PASS for product changes. Retained diff context whitespace was
  normalized and separately checked before publication; see round3-evidence-repair.md.

Exact commands:
```sh
/tmp/hl-trailing-venv/bin/python -m unittest tests.test_conditional_add tests.test_operations_cli -q
/tmp/hl-trailing-venv/bin/python -m unittest tests.test_conditional_add tests.test_strategy_tools tests.test_strategy_signals tests.test_managed_execution tests.test_managed_gateways tests.test_manual_adoption tests.test_native_trailing tests.test_hyperliquid_client tests.test_operations_cli tests.test_risk tests.test_execution_lock tests.test_websocket_streams -q
/tmp/hl-trailing-venv/bin/python scripts/smoke_conditional_add.py
git diff --check
git diff --no-index --check /dev/null reports/sdlc/issue-27/round3-changes.diff
```

AC1/AC4 regression reuse: capital sizing, migration, full-position exits and native
trailing sources are unchanged; their tests are included in the210test scope.
AC2: new table cases cover transient peer recovery across reopen and expiry/kill
switch rejection; hard exit/cancel/intervention flags still reject, even with a
PROTECTED snapshot. Existing grant-revocation/freshness/preflight/replay tests pass.
AC3/AC5: unknown execution cannot resend; status is scoped and does not write the
owner, and local TS continues observing prices. Smoke exercises actual CLI wiring
and partial/complete fill projection. Owner docs updated; no new schema or framework.

Independent verification is recorded separately in round3-independent.md. No real
account/protection, credentials or activation were touched. Unified-USDC-only total
reconciliation and external trailing migration limitations remain as documented.
