# Implementation plan

Owner: main. Notebook: .planning/2026-09-24-issue-27/. Upstream: intent/issue-27.md, specs/issue-27.md. Endpoint local.

1. Add regression fixtures for account totals and add authorization/lifecycle, observe intended failures.
2. Add deterministic capital reconciliation and read-only account evidence collection; adapt strategy sizing.
3. Extend immutable signal authority, tranche storage, supervisor add admission, combined protection and gateway fill reconciliation. Keep existing entry and exit framework.
4. Add focused migration/full-exit tests and an offline CLI/SQLite smoke with stub gateway.
5. Update owner docs and flow diagram, run scope checks, obtain independent verification and correct material findings.

Validation: unittest modules for strategy_tools, strategy_signals, conditional_add, managed_execution/gateways, manual_adoption, native_trailing, hyperliquid_client, operations_cli and risk; scripts/smoke_conditional_add.py; git diff --check. Temporary databases only, no credentials. Rollback: stop new add admissions; existing ownership/protection data remains in additive SQLite tranche table; do not cancel protections as rollback.
