# Investigation

Input: [intent](../../../intent/unified-trading-data.md). Baseline: `623b33392af24c9efeb7acf1c364251e9d7d2ae3` plus existing local account report snapshots. No new broker requests were required.

## Confirmed evidence

| Location | Observation | Design consequence |
| --- | --- | --- |
| `kis_hl/cli.py:107` | Default `--db` is `data/kis_hl.sqlite`. | Retain the path and operator override. |
| `kis_hl/storage.py` | Market, order, journal and asset tables; daily/funding collectors overwrite rows on conflict. | Add revision/lineage semantics before backfill can silently replace historical analysis inputs. |
| `kis_hl/journal_sync.py` | Account-scoped fills, cash costs, cycles, coverage and 10800-second scheduling. | Reuse scope and scheduling contracts; introduce richer cost identity/precision through additive versioned adapters. |
| `kis_hl/journal_history.py` | Funding identity uses hash plus coin; KIS order summaries are unresolved facts. | Do not import those semantics unchanged into the new canonical ledger. |
| `kis_hl/trailing_storage.py`, `managed_execution.py`, `execution_lock.py` | Trading state and local ownership depend on selected database/path. | A reporting migration must not relocate or replace an active supervisor database. |
| `kis_hl/instruments.py`, asset and mapping modules | Analysis references differ from execution listings. | Preserve distinct instruments, provider symbols and time-bounded reference relationships. |
| Local `data/investment-journals/` reports | Separate raw responses, derived exports and SQLite snapshots; some source rows are daily aggregates. | Import raw facts with lineage; keep reports as immutable comparison artifacts, not a second fact source. |
| Observations 0001/0002 | Repeated funding hashes, daily bucket ambiguity, fee inclusion differences, currency-unit ambiguity and unavailable fill times. | Metric-specific eligibility and component-level accounting are mandatory. |

Private report quantities/amounts and account identifiers are deliberately absent from this versionable artifact. The migration manifest will reference private source files by digest, role and account binding.

## Market clarification

The user selected daily/minute candles and periodic quote/funding/order-book snapshots, plus approximately ten years of weekly bars. Exhaustive tick/L2 delta capture is outside the first implementation. Older history depends on listing date, provider retention and interval availability; a requested ten-year horizon is not a promise that every instrument has ten years of observations.

## Storage facts and choices

SQLite WAL permits concurrent readers with one writer; it is a same-host design and does not provide atomic commits across attached database files. Use short bounded market writes and preserve operational priority; a second market database is a later measured scaling decision, not the first migration. See [WAL](https://www.sqlite.org/wal.html).

Backups must use a consistent SQLite backup mechanism, not a bare copy of a live main file. Foreign keys must be enabled on every connection. See [backup](https://www.sqlite.org/backup.html), [foreign keys](https://www.sqlite.org/foreignkeys.html). These are design constraints; current connection settings have not been changed.

## Remaining uncertainty

- Per-provider weekly/minute retention and pagination must be capability-probed during implementation.
- KIS day precision cannot prove exact holding durations; daily source values can still support reconciled monetary PnL.
- Source reporting grain can change between fetches. An hourly and daily view of the same funding period must not be counted twice.
- All-history API reads and quantity agreement do not prove lifetime completeness.
- Full account capital-return calculations require complete deposits/withdrawals/transfers and non-overlapping equity snapshots.
