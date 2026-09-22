# Triage: unified trading data

Mode: plan-only. Change kind: non-executable. Endpoint: local. Owner: /root.
Source: user requests design to connect the default SQLite DB with finalized raw data, journals, analysis inputs and market data.
Repository base: 623b33392af24c9efeb7acf1c364251e9d7d2ae3; branch update-readme-md.
Existing protected-trading SDLC files have unrelated uncommitted changes; preserve them.

Scope is architecture, data contracts, an Archify flow and incremental migration/test plan. No application implementation, data migration, live action, commit, push or PR is part of this request. Private holdings, addresses, credentials and report amounts must stay outside versionable design artifacts.

Acceptance: AC1 authoritative storage and ownership; AC2 evidence-preserving raw/normalized model; AC3 cost/precision/currency-safe journal and analysis; AC4 market identity/history/retention; AC5 reversible idempotent migration and recovery; AC6 traceable diagram and implementation/test plan.

Independent assessment is deferred for this bounded first local design draft; no schema or operational behavior changes. Content checks and diagram checks are required now. A fresh-context independent verifier is mandatory during a later implementation. This is not an independently approved design.

Planning records: .planning/2026-09-13-unified-trading-data/{task_plan,findings,progress}.md.
