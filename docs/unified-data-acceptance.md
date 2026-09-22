# Canonical data release acceptance

This is the current implementation ledger for the broader intent/spec/plan in
`intent/unified-trading-data.md`, `specs/unified-trading-data.md` and
`plans/unified-trading-data.md`. Those documents preserve the accepted design;
this ledger does not silently waive requirements or claim every planned phase is
complete. Operational usage and limitations belong to unified-data-operations.md.

| Contract | Current implementation / outstanding evidence |
| --- | --- |
| AC1 local SQLite, existing execution-state compatibility | Additive v1 schema, checksum validation, read-only status/preview; existing state preserved. No destructive migration. |
| AC2 raw evidence and revisions | Immutable raw bytes, source locators, idempotent import, validated KIS source maturation; ambiguous within-observation daily identities rejected. |
| AC2 recurring sync and audits | Configurable 10800-second default, bounded account overlap, separately configurable history-audit jobs, attempt/success and worker heartbeat. Durable per-page cursor resume remains outstanding; retries replay a bounded request. |
| AC3 account/currency journals | Explicit account selection, actual histories, both-side fees/funding, anchored cycles and separate fee categories. Master never added implicitly. Contradictions are rejected and unresolved groups remain pending. |
| AC3 completeness workflow | Independent bounded statements can reconcile existing facts and inventory. API lifetime retention is never inferred. Transfers/dividends/corporate actions and capital-return inputs remain outstanding. |
| AC3 metric eligibility | Existing nine formulas retained; excluded cycle counts/reasons and holding-eligible counts are exposed. Unknown exact DAY holding time remains null. |
| AC4 market collection | Native weekly ten-year request target, daily/minute, KIS overseas minute adapter, quote/book/funding samples; provider limits recorded. Public HL market collection is explicitly mainnet-only. |
| AC4 variant and analysis validity | Index price basis separated; current derived inputs checked transitively; old exports immutable; late journal inputs trigger freshness updates. Legacy unknown endpoint provenance is not retrospectively certified. |
| AC4 calendars/fallback | Caller-supplied expected sessions support weekly derivation. Automatic exchange-calendar acquisition, full daily/minute gap certification and automatic weekly fallback orchestration remain outstanding. Raw native rows stay usable for retrospective research with these limitations. |
| AC5 backup/recovery/retention | Online backup and isolated restore; immutable exports; pin-aware retention preview. Deletion and storage-pressure automation remain outstanding. |
| AC5 active cutover | Legacy tables remain compatible and separate; coordinated legacy-writer cutover is outstanding. This correction does not change live execution ownership or run production migration. |
| AC6 runtime/CLI | Explicit local commands, read-only previews, scheduler visibility and JSON/HTML exports. Background installation is operator-owned. |
| Protection, notifications and strategies | Protection belongs to prerequisite PR #13. Notifications and future strategy automation were excluded by the user from this task. |

Outstanding design items are visible remaining scope, not evidence of completed
acceptance or an assumed user-approved deferral. These fixes close the accepted
review defects; they do not certify real account retention, entitlement, listing
coverage or live supervisor performance. Synthetic tests, separate real CLI smoke,
and independent verification evidence accompany the correction record in
`reports/sdlc/unified-trading-data-implementation/pr14-review/full-correction/`.
