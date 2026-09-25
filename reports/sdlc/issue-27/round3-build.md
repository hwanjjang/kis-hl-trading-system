# Third review corrections — 2026-09-25

Source: PR30 review5311943048 at cb0baa6. AK accepted implementation of both
recommendations; existing correction/push authority continues, with no merge,
live account mutation or activation. Build iteration4 reuses the canonical issue27
intent/spec/plan and the main-owned notebook; historical local-route receipts
remain historical. Publication authority is recorded in publication.md.

## Requirements and implementation

- AC2: same-account/mode transient DEGRADED and ADOPTING peers defer an unsent
  add without consuming it. Authority, revocation, kill switch and expiry are still
  checked on each tick. Recovery rereads fresh execution facts and creates at most
  one attempt. Exit/cancel, read-failure-exit and native-intervention flags reject
  even when the peer snapshot still says PROTECTED. EXIT_PENDING, EXITING,
  INTERVENTION and unsupported states retain rejection. Finished peers are ignored.
- AC3/AC5: supervisor status and run --once project pending_adds independently of
  owner protection state. Each nonterminal record identifies its tranche, signal,
  status, actual filled quantity, durable attempt and optional wait reason. No DB
  schema/state rewrite, new order path or retry is added. Terminal history remains
  available in order status. Unknown execution remains never-resend after restart;
  existing SL/TS keeps managing observed exposure.
- Owner documentation describes both boundaries. No account-capital, exchange API,
  fill arithmetic, full-position exit sizing or external trail migration changes.
  Existing structural flow/diagram remains applicable; narrow guards and read-only
  projection do not introduce a lifecycle, scheduler or framework.

## Test and smoke design

Reuse ConditionalAddTests fixtures and the existing CLI/SQLite smoke; temp DBs,
stub gateways and no live accounts. Table scenarios cover transient peer recovery
through SQLite reopen; expiry and kill switch while waiting; exit/cancel/recovery
flags including a PROTECTED snapshot; UNKNOWN status scoped to the selected
account and status read without mutation; local TS tracking despite UNKNOWN.
Existing tests cover grant revocation, fresh source/funds/exposure checks,
protection/exit behavior and replay. Independent verification challenges boundaries.

Expanded smoke uses actual CLI handlers and SQLite reopened on every invocation.
The stub accepts the add but loses its acknowledgement: both run --once and status
must display UNKNOWN while current exposure stays PROTECTED. Subsequent readback
shows SUBMITTED with partial fills, then no pending add after terminal fill. It
must retain exactly one send and full combined SL/TS1.5. Socket creation is denied;
TemporaryDirectory cleans the DB. Run python scripts/smoke_conditional_add.py in
/tmp/hl-trailing-venv. A duplicate send, missing pending record, stopped protection,
wrong coverage or network access fails. Run tests and smoke serially for fixture locks.

## Red / Green notes

Initial31test Red:10 intended assertion failures (peer recovery/bounds and pending
exit flags) plus one fixture expiry error, which is not product evidence. The
cross-account fixture expiry was corrected. Replaying the corrected status test
against cb0baa6's isolated cmd_supervisor produced the expected missing pending_adds
KeyError (round3-status-red.log). Its first replay lacked a patched scope function;
that harness error was corrected before recording the successful intended Red.
The first Green uncovered that signal_id belongs to tranche.plan; the projection
was corrected. Final focused Green37tests passed. Test/command output and final
source binding are in round3-verification.md and round3-candidate.json.
