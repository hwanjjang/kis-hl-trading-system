# Post-merge lifecycle verification

Candidate: `86c59c56ab890f884849ec863ccb1de7cd4481ac64aa31ce09c7e8d7779f305a`. Base4b558e0. Source identity includes33files and2obsolete browser
sidecar deletions; diagram screenshots/receipts are evidence, not executable sources.

- Intended Red:8tests,4failures+2missing-field errors; both defects and missing
  durable per-attempt clock reproduced.
- Initial focused Green69tests passed25.410s (before three additional test methods).
- Final lifecycle boundary suite11tests passed5.933s.
- Final changed-scope221tests passed42.753s.
- Expanded offline CLI/SQLite smoke passed after the broad suite: original unknown
  acknowledgement/full1.5SL/native TS lifecycle; historical entry cancel followed
  by a fresh add expiry cancellation with exactly one cancel; late partial fill
  under pending cancel receives1.2SL coverage; terminal unsent add retirement and
  legacy closed-row repair across actual CLI invocations. Socket creation forbidden.
- Product `git diff --check` passes. Retained diff lines are normalized before hashing.
- Both diagrams pass Archify9/9showcase with0errors/warnings, real Chromium viewport
  checks and separate image inspection. Final code/diagram alignment PASS. See
  diagram-review.md, diagram-handoff.json and diagram-source-alignment.md.

Exact main commands:
```sh
/tmp/hl-trailing-venv/bin/python -m unittest tests.test_add_lifecycle -q
/tmp/hl-trailing-venv/bin/python -m unittest tests.test_add_lifecycle tests.test_conditional_add tests.test_strategy_tools tests.test_strategy_signals tests.test_managed_execution tests.test_managed_gateways tests.test_manual_adoption tests.test_native_trailing tests.test_hyperliquid_client tests.test_operations_cli tests.test_risk tests.test_execution_lock tests.test_websocket_streams -q
/tmp/hl-trailing-venv/bin/python scripts/smoke_conditional_add.py
git diff --check
```

AC1 and AC4 behavior is unchanged and included in the broader regression scope.
AC2/AC3: new cancellation target gets a fresh clock; same target keeps its deadline
through retry/reopen/crash; legacy bounds, unknown target and partial-fill SL tested.
AC2/AC5: all three terminal states retire only QUEUED with no durable attempt;
non-QUEUED records, signed UNKNOWN, sizing/history, read-only status remain intact.

Actual Grok independent verification and separate final review remain pending here.
This report does not prove exchange behavior or authorize live activation or merge.
