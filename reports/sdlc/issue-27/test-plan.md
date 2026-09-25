# Offline acceptance scenarios

Use installed /tmp/hl-trailing-venv/bin/python (Python 3.12 with repository SDK dependencies).
All exchange boundaries are stubbed; temporary SQLite and actual CLI handlers are real.
No account credentials or network are prerequisites.

| Scenario | AC | Layer | Expected and failure boundary |
| --- | --- | --- | --- |
| account-total | AC1 | deterministic regression | total1000/capital10000/risk100 regardless of segment; unknown/overlap/wrong account/missing fail |
| add-authority | AC2 | SQLite integration | completed/fresh exact condition, units/SL/expiry/owner; missing/revoked/wrong grants and changed exposure fail; restart cannot resend |
| combined-protection | AC3 | stubbed gateway/supervisor | actual partial/completed add fills and tranche evidence; SL deficit coverage; full native/local TS without resetting prior trails; bounded failure |
| residual-exit | AC4 | supervisor + native adoption/gateway | external percentage migration performs zero mutations; partial native/local exits use residual only; cleanup scoped |
| cli-smoke | AC5 | real CLI/SQLite, stub transport | capture -> preview -> authorization -> add -> partial/completed reconciliation -> reopen replay; one add, SL/TS1.5 |
| scope-regression | AC1-AC5 | unittest | existing entry/adoption/native/CLI/risk behavior preserved |

Initial Red: tests/test_conditional_add.py exposed segment equity fallback and enter-only rejection.
Final tests: `python -m unittest tests.test_conditional_add tests.test_strategy_tools tests.test_strategy_signals tests.test_managed_execution tests.test_managed_gateways tests.test_manual_adoption tests.test_native_trailing tests.test_hyperliquid_client tests.test_operations_cli tests.test_risk -q`.
Separate smoke: `python scripts/smoke_conditional_add.py`; socket creation is forbidden.
Smoke outputs each exact CLI command and validates SQLite reopen on each invocation.
Run tests and smoke serially because fixtures share an account-lock name. Temporary DBs
are removed by their context managers. Retain sanitized logs in this report directory.
Run `git diff --check`. No live-money verification is required or claimed.
