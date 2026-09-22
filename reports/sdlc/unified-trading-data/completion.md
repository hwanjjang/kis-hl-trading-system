# Unified trading data — design completion

Outcome: the local design request is complete. The proposed extension keeps
`data/kis_hl.sqlite` authoritative and connects immutable evidence, revisioned
facts, reconciliation, journals and reproducible analysis. Market storage includes
daily/minute bars, configurable ten-calendar-year weekly backfill, and sampled
quotes, funding and order books. Actual provider coverage remains explicit.

| Acceptance criterion | Design evidence | Assessment |
| --- | --- | --- |
| AC1: storage ownership and mappings | Specification sections 1–3; architecture owner link | Covered |
| AC2: identity, revisions, lineage and precision | Specification sections 2–4 | Covered |
| AC3: costs, accounting, quality and reporting scope | Specification section 5 | Covered |
| AC4: market history and retention | Specification section 6; weekly clarification in intent | Covered |
| AC5: reversible import, migration and backup | Specification sections 7–8; phased implementation plan | Covered |
| AC6: validated diagram and incremental plan | Design receipts, implementation phases and planned acceptance scenarios | Covered |

Deliverables: [specification](../../../specs/unified-trading-data.md),
[implementation plan](../../../plans/unified-trading-data.md),
[interactive data flow](design/dataflow.html), and the proposed-design link in
[architecture documentation](../../../docs/architecture.md).

Actual checks: 19 local Markdown links resolved, 16 JSON artifacts parsed,
eight completed-stage output hashes matched, and `git diff --check` passed.
Archify passed nine deterministic checks and four desktop viewport checks;
recorded image review covers light and dark themes. Source, HTML and review
digests match. See [content checks](content-checks.json) and
[diagram receipts](design/README.md).

This task changes design documentation only. Runtime tests, live API collection,
active database import/migration, commits and PR actions were not performed.
Existing protected-trading worktree changes are outside this task. Provider
history depth, performance targets and accounting integration require execution
of the implementation plan. Independent approval is not claimed; it is deferred
to implementation. No unresolved preference blocks the current design handoff.

The task-observer checkpoint reused existing funding-identity and broker-cost
observations. No new reusable observation was identified beyond those existing
rules; the weekly history duration is a task-specific requirement.
