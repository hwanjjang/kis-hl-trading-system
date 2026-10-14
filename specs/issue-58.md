# Spec — issue 58: fill-triggered journal sync, journal notifications and status

Intent: `intent/issue-58.md` (AC1–AC5). Base `513364d`. One new focused module, `kis_hl/fill_journal.py`, plus small hooks in existing modules. No order, cancel or transfer code path changes.

## Data (one SQLite file, additive tables)

The canonical DDL is checksum-locked (`data_migrations.py`), so new tables are created with `CREATE TABLE IF NOT EXISTS` by `fill_journal.ensure_schema(db)`, the same additive pattern `ExecutionStore` uses. `ExecutionStore.__init__` calls it, so the supervisor process can write requests. Every worker and CLI writer calls it before use. Read-only status treats missing tables as empty.

```sql
journal_sync_requests(            -- one row per venue/account; coalesced pending request
  venue TEXT, account TEXT, scope TEXT NOT NULL,
  pending_since_ms INTEGER,       -- NULL = nothing pending; else earliest range start
  requested_ms INTEGER, request_count INTEGER NOT NULL DEFAULT 0,
  attempts INTEGER NOT NULL DEFAULT 0, next_attempt_ms INTEGER, last_attempt_ms INTEGER,
  last_error TEXT, last_success_ms INTEGER, last_result TEXT,
  PRIMARY KEY(venue, account))
journal_notification_baseline(scope TEXT PRIMARY KEY, after_run_id INTEGER NOT NULL, created_ms INTEGER NOT NULL)
journal_notified(journal_id INTEGER PRIMARY KEY, scope TEXT NOT NULL, notification_id INTEGER NOT NULL)
```

`account` is lower-cased for HL. `scope` is `Scope(venue, environment, account).key`, which equals both the supervisor's `row['scope']` and the canonical account ID.

## AC1 — Recording a sync request in the supervisor

`Supervisor.step` copies the fill markers of the loaded row (`entry_filled`, `observed_size`, `protective_filled`, `exit_protective_filled`, `first_fill_ms`) before `_step`. After the committed reload, it calls `_request_journal_sync(before, after, now)` when any marker changed and the row is live.

The request is:
- venue from the `plan.instrument` prefix (`hl` → `hyperliquid`, `kis` → `kis`)
- account `self.gateway.account`
- scope `after['scope']`
- `since_ms` = the pre-step `last_observed_ms`, falling back to `created_ms`

`fill_journal.request_sync(db, ...)` upserts:
- If nothing is pending, it sets `pending_since_ms=since`, `requested_ms=now`, `attempts=0` and `next_attempt_ms=now`.
- Otherwise it sets `pending_since_ms=min(existing, since)`.
- In both cases it increments `request_count`.

The call is wrapped in `try/except Exception`. A failure logs `journal_sync_request_failed` (exception type only) and returns. It never raises into, delays or changes supervisor state, because it runs after the commit and touches only its own table.

Paper rows never reconcile fills, so they never request. The hook adds one local SQLite write and no network IO inside the account lock.

## AC2 — Processing, retry and fallback

`data_jobs.run_due(store, execute, *, clock=None, before_jobs=None)` gains an optional callable that runs inside the existing `data-jobs` lock, after the heartbeat and before due jobs. `cmd_market` passes `lambda t: fill_journal.process_requests(store, sync, clock=t)`. Fill-triggered work therefore goes ahead of slower jobs, with no second worker or lock.

`process_requests` handles each row with `pending_since_ms` not NULL and `next_attempt_ms <= now`:
1. Remember `request_count`. Call `ensure_baseline(scope)`.
2. Run `sync_account(store, venue, account, start_ms=pending_since_ms - REQUEST_OVERLAP_MS)`, where `REQUEST_OVERLAP_MS` is 15 minutes and the range ends now.
3. On success:
   - Set `last_success_ms=now`, `attempts=0`, `last_error=NULL` and a short `last_result` (counts only).
   - If `request_count` is unchanged, clear `pending_since_ms` and `next_attempt_ms`. Otherwise leave the request pending with `next_attempt_ms=now`, so a fill recorded during the sync gets its own pass.
   - Call `enqueue_journal_notifications(scope)`.
4. On any exception: `attempts += 1`, `last_attempt_ms=now`, `last_error` = exception type name, and `next_attempt_ms = now + min(30 s * 2^(attempts-1), 15 min)`.

Other requests continue. `process_requests` never raises, except for a schema error.

The fallback is the existing `account` job kind, unchanged in scheduling: HL is configured at 300 s and KIS at 3,600 s, with the one-day overlap. `execute_job` gains `ensure_baseline` before the sync and `enqueue_journal_notifications` after it, so unowned and manual fills are notified too. The KIS interval is not session-gated: an hourly job satisfies "≤ 60 min during sessions", and running outside sessions only costs extra reads. `data sync` (manual) uses the same wrapper.

Journals stay unique through the existing fact revisions. Notifications stay unique through `journal_notified`.

## AC3 — Journal notifications in the shared outbox

`enqueue_journal_notifications(store, scope, *, now_ms)` runs one transaction:
- It selects `position_change` analysis runs for facts with `scope = ?`, `run.id > baseline.after_run_id`, and `run.id NOT IN journal_notified`.
- If there are none, it does nothing.
- Otherwise it inserts one `managed_notifications` row and the `journal_notified` keys for each journal in the batch. Because the keys are `INSERT OR IGNORE` primary keys and are checked in the same transaction, a journal can never appear in two batches.

The batch row:
- `position_id='journal-batch:<first journal_id>'`
- `kind='journal_batch'`
- `scope=scope`, `mode='live'`, `episode_ms=now`
- payload: `{venue, account_label, entries:[...]}` with at most 20 entries rendered and `more` for the remainder

`ensure_baseline(scope)` stores the current maximum `position_change` run ID the first time an account is processed. The historical backlog is therefore never announced, and only journals created after enablement are notified. A failed enqueue leaves journals unnotified until the next successful enqueue for that scope, which picks them up because selection is "not yet notified", not "created in this run".

Each entry comes from `position_journal.change_entry`, plus cycle data from `journal_view` for closes:
- `journal_id`, `instrument`, `change`, `signed_quantity`, `price`, `currency`, `event_start_ms`, `time_precision`
- for `close`: `pnl = {status: confirmed|pending, net_pnl, net_return_pct, reasons}`. It is `confirmed` only when the cycle containing the fact is `FINALIZED`.

`notification_message()` gains explicit branches for `journal_batch` and `journal_daily`. Existing kinds are unchanged, and a new unknown kind raises rather than rendering as RECOVERED. Times render in Asia/Seoul:
- `MILLISECOND` precision → `YYYY-MM-DD HH:MM:SS KST`
- anything else → `YYYY-MM-DD KST (<precision> precision)`

No time of day is invented. Hermes keeps using `supervisor notifications --venue V` and `supervisor notification-result`; journal rows share the account `scope`. Delivery remains at least once, which is the existing outbox contract.

## AC4 — `data journal-status`

Usage: `data journal-status [--accounts ID ...] [--as-of-ms N] [--enqueue-summary]`.
- Without the flag it opens `DataStore(readonly=True)`, writes nothing, and prints JSON.
- Accounts default to every `hyperliquid` and `kis` account in the store.

`journal_exports.journal()` is refactored into a pure `journal_view(store, accounts, as_of_ms)`, which returns `(result, fact_ids)`, plus the existing pin. Report output is unchanged.

Per account, the status reports:
- `account`, `label`, `venue`
- `open_positions`: OPEN cycles with instrument, side, quantity (entry − exit), opened time and precision
- `today`: position changes with `event_start_ms` on the current KST date
- `cycles`: closed counts by status, plus `statistics` = `journal_exports.statistics(closed cycles)`, the nine statistics. These use FINALIZED cycles only and report the excluded count, so they are empty or pending rather than fabricated.
- `pending`: counts of reasons across non-finalized cycles (`inventory_unanchored`, cost reasons, `trade_coverage_unverified` / `cash_coverage_unverified`, funding), plus `quality_findings` kinds
- `sync`:
  - the request row (pending since, attempts, last error, last success)
  - account jobs (interval, last success, last reason)
  - the latest failed coverage row
  - `worker_last_seen_ms`

`--enqueue-summary` opens a writable store and, for each account, inserts one `kind='journal_daily'` outbox row with `position_id='journal-daily:<KST date>:<scope[:12]>'`. The same KST date never duplicates. The message is rendered from the same status JSON. Hermes schedules this after the US close; the repository adds no scheduler.

## Failure behavior and observability

| Failure | Behavior |
|---|---|
| Request write fails in supervisor | Logged; supervisor continues unchanged; the next fill or the fallback job covers it |
| Worker not running | Requests stay pending, visible in `journal-status.sync` with age |
| Sync fails | Backoff retry; `last_error` and coverage `failed` row visible |
| Enqueue fails after sync | Journals stay unnotified and are picked up by the next enqueue |
| Hermes send fails | Existing `notification-result --result failed` path; retried by Hermes |

## Security

Payloads hold instrument, quantities, prices, PnL and the account label only. No addresses, keys or raw API bodies. Errors store exception type names only.

## Alternatives rejected

- **Synchronous sync inside the supervisor:** network IO under the account lock could delay protection, which AC1 forbids.
- **A second worker or daemon:** D2 chose `market collect`.
- **One outbox row per journal:** the issue asks for one message per batch. Per-journal dedupe is kept through `journal_notified`.
- **Changing the checksum-locked canonical DDL:** this would break existing databases.

## Verification strategy

- **AC1:** unit tests using the fake `Gateway` in `test_managed_execution.py`:
  - entry fill → one pending request after commit
  - second fill → still one row, `request_count` 2
  - paper or no fill → none
  - a raising `request_sync` leaves the returned row identical to a run without the hook
- **AC2:** `process_requests` with a fake sync covering success clears, a failure backoff schedule, a request arriving during sync staying pending, and an account job enqueueing. Idempotence through a repeated `sync_account` over the same HL fills, reusing the `test_position_journal` helpers.
- **AC3:** enqueue dedupe and baseline; message rendering for entry, increase, reduction, close (confirmed and pending), reversal and KIS DAY; Hermes list/ack through the CLI.
- **AC4:** a fixture DB with HL and KIS facts; `journal-status` fields; the read-only DB file is unchanged (mtime and bytes); summary enqueue idempotent per day.
- **AC5:** full suite, all CI smoke scripts, a new `scripts/smoke_fill_journal.py` (real SQLite, CLI processes, fake exchange clients, network forbidden), and a diff review for order paths.
