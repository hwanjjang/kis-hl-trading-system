# Issue 59 specification

Input: intent/issue-59.md. Applies to the shared `Supervisor` for Hyperliquid and KIS.

## Read outage (snapshot raises `RuntimeError`/`OSError`)

- Never set `exit_requested_ms` or `read_failure_exit`, and never send anything. This holds for any failure count or duration and in any execution session.
- Record a sanitized `last_error` (unchanged). Increment `read_failures` and keep `read_failure_since_ms`. Maintain `read_health` = {status `unavailable`, since_ms, last_failure_ms, consecutive_failures, last_success_ms, operation `account_snapshot`, phase (gateway reconciliation phase or null), error}. The `error` field uses an allowlisted class category, kind ∈ {http, timeout, transport, other} and an integer HTTP status in 100–599 or null. It never carries a message, URL or payload.
- Owners in INTERVENTION keep their state and reason; only read health and the event are saved. All other owners become DEGRADED. The reason states that this is a warning only, that no exit was requested, that native orders are retained and that local supervision is paused.
- Explicit exit requests, exits triggered independently before the outage, and their deadlines and attempts are left untouched. Recovery may still execute them within their original budget.
- On a failed tick, set `last_supervised_ms` = now. If the gateway exposes `observation_gap_ms(row, start, end)` (KIS local SL), keep the maximum gap between consecutive supervisor ticks in `unsupervised_gap_ms`. The KIS gateway measures the next gap from max(`last_observed_ms`, `last_supervised_ms`). The supervisor applies max(snapshot gap, `unsupervised_gap_ms`). As a result, time spent failing reads is never counted, while process downtime keeps the existing observation-gap policy. `same_execution_session` still uses `last_observed_ms`.
- HL gateway: the phase is `metadata` during `_market` and `orders` afterwards. `TransientInfoError` carries `kind` and `http_status`, and a non-transient HTTP `RuntimeError` carries `http_status`.

## Recovery (snapshot returns)

- Reset the read-failure counters and clear the gap anchor and accumulator. If an episode was open, close `read_health` (status `ok`, last_success_ms, last_outage summary) and queue one `read_recovered` notice. The notice is persisted with the state and reason of the transaction that writes it, after the checks that follow. Inconsistent evidence therefore yields a notice whose state is INTERVENTION.
- A legacy `read_failure_exit` flag with residual size enters INTERVENTION with reason "Legacy read-outage exit latch retained; explicit scoped withdrawal or exit decision required". It does not enter EXITING and sends no order. When the owner is flat, the flag is cleared and normal cleanup runs.
- The generic exception handler no longer removes `read_failure_exit`, which preserves provenance.

## Notifications (additive table `managed_notifications`)

Columns: id, position_id, scope, mode, kind ∈ {read_outage, read_recovered}, episode_ms, created_ms, payload, delivered_ms, delivery_attempts, last_attempt_ms, with UNIQUE(position_id, kind, episode_ms). The supervisor appends `pending_notifications` to the row. `ExecutionStore.save` inserts them with INSERT OR IGNORE in the same transaction as the state, so polling, restarts and version races cannot create duplicates.

The payload is built from allowlisted fields only: instrument, venue, kind, episode_ms, state, reason, read_health, native orders retained (owned open stop/trailing IDs), local protections impaired, and `local_supervision` = `paused`.

CLI:

- `supervisor notifications --venue V [--live]` lists undelivered rows with a fixed English message. It is read-only.
- `supervisor notification-result --venue V --notification-id N --result delivered|failed` records delivery (`delivered_ms`) or a failed attempt (count plus time). It never affects execution.
- `supervisor status` shows `pending_notifications`.

## Intervention blocker and diagnostics

- `_state` no longer replaces the reason. `first_intervention` keeps the first cause (setdefault). `ExecutionStore.save` maintains `intervention_blocker` = {reason, since_ms} while the state is INTERVENTION, updates it when the reason changes and drops it when the owner leaves INTERVENTION.
- `owner_diagnostics(store, row, now)` is read-only and appears in `order status` and per position in `supervisor status`. It reports:
  - `intervention` {first_cause, current_blocker}
  - `read_health`
  - `supervision` {native_orders_retained, local_supervision active/paused/not_applicable, reason}
  - `exit` {requested_ms, deadline_at_ms, deadline_exhausted, exit_attempts, max_exit_attempts, attempts_exhausted, provenance}
  - `events` {total, polls, recent_transitions}, where a transition is a change of state or reason from the previous event (SQL LAG)
- Exit provenance has three values. `operator` comes from the `exit_request_source` that `request_exit` records. `read_outage_latch` comes from the legacy flag or is inferred from an INTERVENTION event at `time_ms == exit_requested_ms` whose reason starts with "Account snapshot unavailable". Anything else is `other`.

## Recover and withdraw

- `order recover` refuses with an explanation when residual exposure has an exhausted exit deadline or attempt budget, or a pending legacy flag. The explanation names the provenance and the exact withdrawal command if the provenance is a read-outage latch. Otherwise recovery is unchanged.
- `order withdraw-read-exit --id ID --exit-requested-ms MS` succeeds only when all of the following hold:
  - the owner is in INTERVENTION;
  - MS matches the request exactly;
  - the provenance is `read_outage_latch`;
  - no exit attempt was created at or after MS;
  - no UNKNOWN or unresolved entry/add attempt exists;
  - no stop or trailing attempt is FILLED and no protective fill is recorded;
  - `cancel_entry` is false.
  
  On success it clears the request and flag, appends to `withdrawn_exit_requests`, keeps the owner in INTERVENTION and requires a separate `order recover`. It never renews budgets, never sends anything and acts on exactly one owner.

## Verification

Use offline fakes only: the existing managed-execution Gateway and the KIS fixture gateway. Add a new offline smoke script that drives the CLI against a temporary SQLite database with a scripted gateway. Fail-closed paths (identity, foreign orders, UNKNOWN) keep their existing tests. Rollback is a code revert. The table is additive, and the new row fields are ignored by older code. A legacy flag left by older code is handled as described above.
