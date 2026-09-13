# Unified trading data implementation — completion

Outcome: local implementation and initial data connection complete. The existing
`data/kis_hl.sqlite` now holds immutable evidence, normalized revisions, coverage,
KIS/tradefi and combined journal runs, market history/snapshots, and pinned weekly
analysis. Existing operational tables were preserved. The exact code candidate is
in candidate.json. The independent verdict is PASS with no unresolved Must Fix.

| Criterion | Outcome and actual evidence |
| --- | --- |
| AC1 | Additive SQLite schema and stable account/instrument identity implemented; operational table counts preserved; source-only manifest avoids treating old reports as trades |
| AC2 | Immutable byte evidence, source observations, Decimal validation, scoped business identities, correction revisions and transitive analysis lineage tested |
| AC3 | Existing private KIS/tradefi fee, funding and currency totals reconciled; closed-cycle boundaries restored, shared funding remains pending, DAY precision preserved; independent long/short partial-exit conservation passes |
| AC4 | Native 1w/1d/1m collection and sampled book/quote/funding implemented; ten-calendar-year target configurable, actual history and missing weekly ranges explicit; native non-ISO weekly anchor and DST tested |
| AC5 | Preview/apply, duplicate replay, runtime failure receipts, consistent backup and isolated restore verified; retention deletion disabled; representative concurrent SQLite write load passed the declared latency target |
| AC6 | CLI usage documented; real subprocess storage/report/analysis smoke and real read-only minute polling smoke passed; initial market collection and four pinned analyses completed |

Verification: 308 tests passed in the independent final full suite; targeted
Green/post-refactor checks and additional real CLI smoke passed. All seven review
findings were resolved and rechecked. Diagram validation from the accepted design
remains applicable to the unchanged logical flow. No signed trading action was
performed. No commit, push, PR or merge occurred at this local endpoint.

Private rollout receipts, generated journals, source manifest, analysis outputs
and actual market coverage are under ignored `data/unified-trading-data/` and
`data/investment-journals/`. Persistent pre/post/final online backups are outside
the worktree under `/root/.local/state/kis-hl/backups/`. Final integrity and foreign
key checks passed; isolated restored fact counts matched the active database.
The currently configured KIS account matches the four visible digits in the
captured masked source label. This is a suffix consistency check; the full native
identity comes from the existing operator configuration, not the masked label.

Account sync cadence is configured to 10800 seconds. Market jobs have separate
cadences; recurring minute polling uses the last successful cursor with overlap.
**No continuous collector process is running.** Run the documented CLI collector
under the user's chosen process supervisor to maintain periodic collection.
Configuration/import does not install or start a host service automatically.

Limits: provider listing/history may be shorter than requested; equity calendar
completeness is not independently certified. KIS overseas minute data, automatic
portfolio cash-flow returns, full corporate-action accounting, predicted funding,
exhaustive ticks/L2 and persistent host-service deployment remain outside this
first implementation. Legacy CLI tables remain compatibility interfaces; the new
canonical commands are the documented collection/analysis path. These boundaries
are explicit in docs/unified-data-operations.md and are not claimed implemented.

Observer checkpoint: the native-period-anchor lesson was recorded for later skill
methodology review; provider-specific observed behavior was documented with the
implemented endpoint changes. No unrelated protected-trading files were modified
by this task.
