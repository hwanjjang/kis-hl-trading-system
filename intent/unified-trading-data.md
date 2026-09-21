# Intent: unified trading data

Status: implementation delivered in PR #14; broader-design acceptance remains partial. See [acceptance ledger](../docs/unified-data-acceptance.md). Task: `unified-trading-data`. Owner: /root.
Authority: user requests design first; latest clarification requires daily/minute/weekly candles, sampled quotes/funding/order books, and approximately ten years of weekly history. Endpoint: local plan-only.

## Problem and outcome

The default operating database and private account-journal snapshots are disconnected. Existing collectors store useful market data, but source identity, corrections, cost breakdown, coverage and report lineage are inconsistent. Establish one canonical local data contract so an account fact is imported once, corrected explicitly, reconciled to its source, and reused by journals, analysis and market-data consumers.

## Scope

- SQLite at `data/kis_hl.sqlite`; existing CLI-first execution and account locks remain.
- Immutable source evidence; versioned normalized facts; quality/coverage; account, instrument and currency identity.
- Account fills, KIS daily statements, actual fees/taxes/funding, positions, cash movements and future capital-return prerequisites.
- Journals by account and consolidated membership; strategy/analysis provenance and reproducible report versions.
- Daily, minute and weekly bars; configurable ten-year weekly target; periodic quote, market funding-rate and top-of-book snapshots.
- Import of the existing local KIS/tradefi artifacts with monetary reconciliation and report regeneration. Master metadata may exist, but Master journal membership remains disabled.

## Acceptance criteria

| ID | Observable design outcome |
| --- | --- |
| AC1 | Explicit canonical store, module ownership and mapping from every current table/report family. |
| AC2 | Raw and normalized identity, immutable revisions, lineage, pagination, retries, corrections and precision are specified. |
| AC3 | Fees/funding/settlements, shared buckets, metric-specific eligibility, accounts and currencies remain correct and distinguish unknown from zero. |
| AC4 | Weekly ten-year coverage, daily/minute bars, sampled market data, sessions/adjustment/provenance and bounded retention are specified. |
| AC5 | Existing artifacts can be migrated twice without duplicate facts; cutover/rollback preserve operating locks and durable writes. |
| AC6 | A checked Archify flow, ordered file-level implementation plan and meaningful acceptance scenarios accompany the spec. |

## Limits and risks

This turn designs the work. It does not alter application behavior, ingest data into the active database, enable a collector, trade, publish private records, commit or open a PR. Notifications remain undecided. Exact fill times, gross hourly funding, older market history and strategy attribution must not be fabricated. SQLite workload isolation, market revisions and safe rollback require explicit tests before implementation.

Related: [spec](../specs/unified-trading-data.md), [plan](../plans/unified-trading-data.md), [SDLC record](../reports/sdlc/unified-trading-data/triage.md).

## 2026-09-20 correction authority

The user authorized fixing PR #14 review G1 and the assessed operation documentation/backup issues, followed by commit and push to `feature/unified-trading-data`. Preserve source evidence and old reports. No live collection, merge or deployment. The existing implementation task and stage counters continue; no new formal PR-review PASS is claimed.
