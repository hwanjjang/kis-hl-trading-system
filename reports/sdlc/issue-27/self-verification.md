# Issue 27 local verification

Outcome: all five offline acceptance criteria pass. No live account reads, signed
venue requests, live protection changes, activation, publication or merge occurred.
The default Python lacks the optional trading SDK; checks used the existing
`/tmp/hl-trailing-venv/bin/python` environment. Unit order logs are stub events.

| Check | Exact command | Outcome |
| --- | --- | --- |
| Initial regression | `python3 -m unittest tests.test_conditional_add -q` | Intended Red: total-balance fixture used segment equity; add was entry-only. 5 tests, 6 assertion failures and 2 expected unsupported-path errors. `red.log` |
| Initial implementation | `/tmp/hl-trailing-venv/bin/python -m unittest tests.test_conditional_add tests.test_strategy_tools tests.test_strategy_signals tests.test_managed_execution tests.test_managed_gateways tests.test_manual_adoption tests.test_native_trailing tests.test_hyperliquid_client tests.test_operations_cli tests.test_risk -q` | 181 passed at that revision; retained historical `green.log`. Later corrections supersede this candidate. |
| Final independent candidate | See `independent-verification.md` final exact command | 184 passed; independent boundary probes verified all four findings corrected. |
| Final scope + account lock regression | `/tmp/hl-trailing-venv/bin/python -m unittest tests.test_conditional_add tests.test_strategy_tools tests.test_strategy_signals tests.test_managed_execution tests.test_managed_gateways tests.test_manual_adoption tests.test_native_trailing tests.test_hyperliquid_client tests.test_operations_cli tests.test_risk tests.test_execution_lock -q` | **185 passed**, 25.333s, exit 0. `post-refactor.log` |
| Additional CLI/SQLite smoke | `/tmp/hl-trailing-venv/bin/python scripts/smoke_conditional_add.py` | Passed, exit 0. `smoke.log` contains exact CLI invocations. |
| Whitespace | `git diff --check` | Passed, exit 0. |
| Diagram | Archify deliver + visual-check with installed cached Chromium | 9/9 checks; four desktop sizes without overflow; light/dark screenshots visually inspected. See `design.md`. |

The smoke executes `account capital`, `order preview`, `signal execute --manual
--live`, `supervisor run --live --once` and `order status` through the real CLI and
SQLite. **Its --live flag selects a stub gateway only; socket creation is forbidden.**
It reopens a temporary DB per CLI invocation. Observed total=1000, capital=10000,
approved add quantity=.5, exactly one add attempt, actual combined position=1.5,
verified fixed SL/native TS coverage=1.5, state=PROTECTED. Replaying authorization
returns the original tranche. Temporary DB/files are cleaned automatically.

AC mapping and findings: see `test-plan.md` and the separate independent report.
Focused tests also cover unknown outcomes across reopen, unapproved migration with
zero mutations, partial original entry/cancel followed by add, authority expiries,
revoked/entry-only grants, changed shared protection bounds, insufficient funds,
protection rejection, full residual exit after competing fills and scoped cleanup.

Updated shared API and strategy skills resolve to the same canonical `.agents`
files from both `.codex/skills` and `.claude/skills`; read/byte equality was checked.
Their deterministic companion commands run in the tests/smoke. These reference-only
updates add no hooks or host runtime configuration. No cross-provider review or
live exchange equivalence is claimed.

Limitations: automated total sizing currently supports verified unified accounts
with USDC as the only nonzero balance. Other modes/valuations fail closed. Native
adds require preserved local backup; external percentage TS needs a supported
explicit migration, which this issue does not supply. Actual concurrent native
orders, trigger fills, mode transitions and directional buying power remain live
uncertainties. The prior ETH conversation remains unarmed. Issue 28 half exits are
not implemented. Source identity: `candidate.json`.
