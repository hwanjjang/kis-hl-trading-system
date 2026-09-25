# Spec: PR #32 review corrections

## Requirements
- R1 (AC1): After each supervisor step on an unfinished owner, a `QUEUED` tranche with no durable attempt and `now >= plan.expires_ms` becomes `EXPIRED` with `retired_ms` and an owner-state reason. This applies whenever the add was not evaluated this tick, including a `PROTECTED` owner with `cancel_entry`. An evaluated `PROTECTED` owner still rejects the expired add in `_try_add` (`REJECTED`). Docs, the add-termination diagram and the PR text describe exactly this.
- R2 (AC2): Wording states "opens no additional retirement transaction (no write lock or attempt scan) when no `QUEUED` tranche remains". Heartbeat writes are unaffected and not denied.
- R3 (AC3): `ExecutionStore.save(self, row, now_ms)` takes no default. Every caller passes an explicit time.
- R4 (AC4): The rollback test identifies the tranche by the `authorize()` return id.

## Interfaces and failure behavior
Only `save()` changes its signature. A missing `now_ms` fails fast with `TypeError` before any write. There are no data, migration or observability changes.

## Alternatives
Restricting expiry retirement to non-`PROTECTED` owners was rejected: it would keep an expired add pending indefinitely while `cancel_entry` holds the owner `PROTECTED`.

## Verification
Red: a new test asserting that `save()` without `now_ms` raises `TypeError` fails on 21f73f1. The `PROTECTED` + `cancel_entry` test pins the current behavior and passes on 21f73f1. Green: targeted and full unittest suites. Smoke: `scripts/smoke_conditional_add.py`. Document checks: `git diff --check`, Archify validate, deliver and visual-check.
