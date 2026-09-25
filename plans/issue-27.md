# Implementation plan

Owner: main. Notebook: .planning/2026-09-24-issue-27/. Upstream: intent/issue-27.md, specs/issue-27.md. Endpoint local.

1. Add regression fixtures for account totals and add authorization/lifecycle, observe intended failures.
2. Add deterministic capital reconciliation and read-only account evidence collection; adapt strategy sizing.
3. Extend immutable signal authority, tranche storage, supervisor add admission, combined protection and gateway fill reconciliation. Keep existing entry and exit framework.
4. Add focused migration/full-exit tests and an offline CLI/SQLite smoke with stub gateway.
5. Update owner docs and flow diagram, run scope checks, obtain independent verification and correct material findings.

Validation: unittest modules for strategy_tools, strategy_signals, conditional_add, managed_execution/gateways, manual_adoption, native_trailing, hyperliquid_client, operations_cli and risk; scripts/smoke_conditional_add.py; git diff --check. Temporary databases only, no credentials. Rollback: stop new add admissions; existing ownership/protection data remains in additive SQLite tranche table; do not cancel protections as rollback.

## Post-merge correction plan

Reuse issue27 counters and notebook. Branch fix/issue-27-add-lifecycle starts at
4b558e0. Issue comment5827258589 records the reproduced defects.
1. Regression tests reuse existing conditional-add stub fixtures: historical
   canceled entry then a later add; cancellation retry/deadline after reopen;
   matching-target legacy clock; lost ack/process death; partial fill during cancel.
2. managed_execution.py: per-attempt cancel_started_ms plus legacy evidence recovery;
   terminal unsent-tranche cleanup with an attempt-existence guard and restart repair.
3. Tests for normal closure, already-closed rows, idempotency, signed/UNKNOWN records
   and read-only pending status; extend existing offline CLI/SQLite smoke.
4. Update owner operations docs and two Archify diagrams; compare final source to
   validated diagrams. No schema migration, scheduler, raw trading path or half exits.
5. Run changed scope tests, separate socket-forbidden smoke and diff check. Obtain
   actual Grok4.7/high/auto independent verification and a separate review; preserve
   effective settings and user override instead of pretending the medium default.
6. Commit/push follow-up PR and report CI/review. No merge or live activation.
Rollback must retain verified protection and durable signed attempts; never cancel
existing protection or replay an UNKNOWN order as a code rollback.
