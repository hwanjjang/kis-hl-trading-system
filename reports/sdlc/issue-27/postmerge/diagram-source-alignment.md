# Final diagram-to-source alignment

Result: PASS. The final implementation inspected on 2026-09-25 agrees with the
previously confirmed design and both delivered diagrams. No source, diagram,
HTML, historical design receipt or historical handoff edits were necessary.
This record closes the design-time source-alignment caveat in `diagram-review.md`
and `diagram-handoff.json` for the exact file bytes listed below. It does not
supersede their original deterministic/browser evidence.

## Inspected implementation boundaries

- `kis_hl/managed_execution.py:18`: FINISHED is exactly CLOSED, REJECTED and
  PREVIEWED, matching the focused terminal-owner node.
- `kis_hl/managed_execution.py:252`: `retire_unsent_adds` begins a SQLite immediate
  transaction, checks the persisted terminal owner, collects durable matching
  tranche IDs from attempts, and changes only QUEUED tranches without a matching
  attempt to CANCELED with owner-state reason and retired_ms. Other status/history
  data is retained. No gateway operation occurs in this cleanup.
- `kis_hl/managed_execution.py:334`: terminal saves invoke that cleanup after the
  owner save. `Supervisor.step` at line 459 invokes it at the FINISHED short-circuit,
  before gateway reads, repairing previously finished rows and a crash between
  save and retirement. These correspond to the focused local-repair card.
- `kis_hl/managed_execution.py:925`: expiry/exit/cancel selects active target attempts.
  Each attempt receives its own durable cancel_started_ms before missing-target
  intervention or cancel submission. Matching-target cancel history supplies the
  earliest legacy start; an owner timestamp is accepted only within the target's
  creation-to-first-cancel interval. Unmatched old owner timestamps cannot consume
  a new add budget. Deadline and attempt caps stay bounded; missing target or
  exhausted budget enters INTERVENTION. Cancellation retries require a prior known
  REJECTED outcome. `update_attempt` at line 376 changes both the in-memory attempt
  and persisted snapshot, so the subsequent budget check uses that target's clock.
- `kis_hl/operations_cli.py:588`: supervisor status reads positions/tranches and
  filters terminal statuses without calling retirement. `run --once` invokes the
  supervisor before reading pending adds. Thus repair remains a supervisor action,
  and preserved UNKNOWN attempts remain available rather than being hidden by
  unsent cleanup.
- `docs/trading-operations.md:662` and `:834`: operational documentation matches the
  per-target budget, restart/legacy rules, acknowledgement versus terminal readback,
  unsent-only retirement and read-only status behavior.

The focused cancellation lane depicts its supported path and concise guards;
missing-target and exhausted-budget intervention branches are documented in the
owner operations document and diagram review, not drawn as a separate exhaustive
state machine. The terminal lanes are deliberately separate because canceling an
add does not necessarily close the position owner. The overview's successful full
protection path remains separate from expired-remainder cancellation. No diagram
claims that cleanup authorizes a new attempt or that a cancel acknowledgement
proves terminality.

## Artifact identity

Recomputed both diagram source and HTML SHA-256 values against their frozen
`diagram-*-deliver.json` receipts: all four match. Existing showcase 9/9,
automated-browser pass and image-based perceptual pass remain bound to these same
bytes. This bounded source-alignment pass did not execute tests, rerender HTML,
exercise live exchange behavior or change repository implementation. Interactive
search/focus/export limitations recorded in the earlier review remain unchanged.

| Inspected path | SHA-256 | Bytes |
| --- | --- | ---: |
| `kis_hl/managed_execution.py` | `2d95773800873dbd7f0d8407f1b54762789348ddfb5ed24df929a887775b697f` | 56178 |
| `kis_hl/operations_cli.py` | `1638cae6bf9a23cd4bbf72b9460f358909b61527f754cd62a01a309035080b9d` | 31465 |
| `docs/trading-operations.md` | `e5694dc19f059bb07a663de492982418ab4e516c5fddc67628a6811c31de3ea5` | 60101 |
| `docs/architecture.md` | `51063de2ddc47933209b2b54d76343a0f91905e1bbf1561c0942227f7a8643aa` | 25173 |
| `docs/architecture/conditional-add.workflow.json` | `64d9e0b83ff32614c2b8e0c16f32a8ed95b80618d986e28697b282bb609e3fed` | 4527 |
| `docs/architecture/conditional-add.html` | `ac1bea56855334d238220b78891c85a915f5c5662383084d9cbf4a93344bb2ca` | 810564 |
| `docs/architecture/add-termination.workflow.json` | `3505e8b2d39c440fe6f2a46770785eae7764f4150579b2aa00195eb3bc77f4b1` | 3589 |
| `docs/architecture/add-termination.html` | `400f3c32c637d8793149afe6b6360760a24c3ece2a0ecddf7aeed07b4c4d090c` | 806205 |
