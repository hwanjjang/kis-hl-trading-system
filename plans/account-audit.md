# Account audit implementation plan

Execution notebook: `.planning/2026-09-13-account-journals/task_plan.md`, owner /root.
Stable SDLC task: on-demand-sync-backup-policy; scope extended without resetting
existing iteration history. Endpoint: update PR19, no merge readiness claim.

Add account capture and audit modules, register three data CLI subcommands, reuse
existing source normalizers, SQLite transaction support and journal generation.
Add tests before implementation and retain intended-Red evidence. Add a separate
standalone synthetic smoke runner with real CLI subprocesses and temporary state.
Update README, operations documentation and journal contract when relevant. Keep
Archify JSON/HTML for the capture/compare/apply boundary. Review existing modules
instead of duplicating signing, endpoint, normalization or journal logic.

Risks: comparing mismatched grains, double-counting funding, promoting API coverage,
stale apply, partial writes, leaking source data, incorrect same-time ordering.
Fail closed on unresolved mismatches; pin reviewed inputs, validate all before a
transaction and verify current DB state again inside it. Rejected alternative:
commit account-specific scripts or silently run the existing mutating sync as audit.
Rollback is code revert; existing source facts and report IDs remain immutable.
No schema migration is required. Prove local behavior with targeted tests, full
regression and independent synthetic CLI smoke before commit/push/PR update.
