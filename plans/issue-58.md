# Plan — issue 58

Inputs: `intent/issue-58.md`, `specs/issue-58.md`, design `reports/sdlc/issue-58/design/` (Archify sequence). Base `513364d`, branch `feat/issue-58-fill-journal`.

## File operations

| File | Change |
| --- | --- |
| `kis_hl/fill_journal.py` (new) | `ensure_schema`, `request_sync`, `process_requests`, `ensure_baseline`, `enqueue_journal_notifications`, `sync_and_notify`, `journal_status`, `enqueue_daily_summary`, `journal_message`, `daily_message` |
| `kis_hl/managed_execution.py` | `ExecutionStore.__init__` calls `fill_journal.ensure_schema`; `Supervisor.step` takes a pre-step marker snapshot and calls a guarded `_request_journal_sync` after the committed reload; `notification_message` gets explicit `journal_batch` / `journal_daily` branches and rejects unknown kinds |
| `kis_hl/data_jobs.py` | `run_due(..., before_jobs=None)` runs inside the existing lock |
| `kis_hl/data_cli.py` | `execute_job` account branch → `sync_and_notify`; `cmd_market` passes `before_jobs`; `data sync` → `sync_and_notify`; new `data journal-status [--accounts] [--as-of-ms] [--enqueue-summary]` |
| `kis_hl/journal_exports.py` | Extract the pure `journal_view()`; `journal()` = view + pin (output unchanged) |
| `tests/test_fill_journal.py` (new) | AC1–AC4 unit and integration tests |
| `scripts/smoke_fill_journal.py` (new) + `.github/workflows/tests.yml` | CLI smoke on a temporary DB with fake exchange clients and sockets forbidden |
| `docs/unified-data-operations.md` | Replace "Current operating policy: user or agent initiated" with the fill-triggered and fallback policy, latency bounds and failure behavior |
| `docs/trading-operations.md`, `docs/product/trading-notifications.md` | Journal notification kinds through the shared outbox (Hermes list/ack) |
| `docs/architecture.md`, `docs/architecture/fill-journal.sequence.json` + `.html` | Module responsibility rows and the maintained diagram, refreshed with repository evidence |
| `README.md` | `data journal-status` and `market collect` account-job usage |
| `.agents/skills/trade-journal/SKILL.md` (+ reference) | `journal-status` statistics semantics (FINALIZED only, pending otherwise) |
| `AGENTS.md` | Ownership row for the journal sync / notification policy (`docs/unified-data-operations.md`) |
| `docs/manuals/journal-status/usage.md` + `.pdf` + capture PNG, `scripts/render_manual_pdf.py` | Manual with actual CLI output; committed PDF generator |

## Order and dependencies

1. **Red tests** in `tests/test_fill_journal.py` for:
   - request coalescing and the supervisor hook (AC1)
   - processing, backoff and fallback (AC2)
   - enqueue, dedupe, baseline and messages (AC3)
   - status and summary (AC4)

   Run them and confirm they fail because the module and behavior are missing, not because of setup errors. Assertion-level Red is preferred: existing-API tests fail on assertions first.
2. **`journal_view` refactor:** the existing journal tests stay green, proving behavior is preserved.
3. **`fill_journal` module and schema; `ExecutionStore` init.**
4. **Supervisor hook and `notification_message` branches.**
5. **`run_due` `before_jobs`; `data_cli` wiring and the `journal-status` CLI.**
6. **Green:** the new tests, then the full suite and all CI smokes.
7. **Smoke script** `scripts/smoke_fill_journal.py`, run in separate processes through the real CLI (`market collect --once`, `supervisor notifications`, `data journal-status`).
8. **Docs, maintained diagram (Archify, with repository evidence), manual capture and PDF.**
9. **Self-verification, commit, push, PR (`Refs #58`), CI, Codex review, corrections.**

## Test commands

```bash
python -m unittest tests.test_fill_journal -q
python -m unittest discover -s tests -t . -q
for s in protected_trading take_profit account_audit manual_handoff timing_opinion read_outage fill_journal; do PYTHONPATH=. python scripts/smoke_$s.py; done
```

(`take_profit` exists only after #57 merges; run the scripts present on this branch.)

## Migration and rollback

- **Migration:** additive `CREATE TABLE IF NOT EXISTS` only. Canonical DDL and checksum are unchanged, and existing databases need no migration.
- **Rollback:** revert the commit. The extra tables are inert to older code. Pending requests are then simply unprocessed; the existing manual `data sync` remains.
- **Operations:** nothing activates until `market collect` runs with account jobs (cutover, separately approved).

## Blast radius and risks

- **What could break:** the supervisor step. The hook runs after the commit inside `try/except Exception`, does one local SQLite write, and has a test asserting an identical result when the hook raises.
- **Riskiest part:** notification dedupe and baseline under concurrent writers (worker plus manual `data sync`). Guarded by `journal_notified` primary keys inside one `BEGIN IMMEDIATE` transaction, with a concurrency test.
- **Also exposed:** `run_due` and `cmd_market`, but the new callable is optional and its errors are contained per request.
- **#57 overlap:** `managed_execution.py` (`step`, `notification_message`) and `operations_cli.py` (not changed here). Expect a small textual merge.
- **Rejected alternative:** a separate fill-sync daemon or synchronous sync in the supervisor, for the lock and latency reasons in the spec.
- **Proof:** Red → Green tests per AC, the CLI smoke in real processes, the full suite plus all CI smokes, and a different-provider review.

## User scenarios

Stored in `reports/sdlc/issue-58/user-scenarios.json` (S1–S5), mapped to tests and manual sections:

| Scenario | Who | What | ACs |
|---|---|---|---|
| S1 | AK, HL supervisor | Supervised HL entry fill → request → worker sync → journal → batch notification listed and acknowledged by Hermes | AC1, AC2, AC3 |
| S2 | AK | Manual exchange-app trade → fallback account job → journal → notification, with no duplicates on the next run | AC2, AC3 |
| S3 | Operator | Worker sync fails (exchange timeout) → backoff, `last_error` visible in `journal-status` → later success clears it | AC2, AC4 |
| S4 | AK, KIS | KIS DAY statement close → notification labels DAY precision and pending PnL | AC3 |
| S5 | Hermes (daily) | After US close: `data journal-status --enqueue-summary` → one `journal_daily` per KST date with stats and pending items; the read-only run leaves the DB unchanged | AC4, AC5 |
