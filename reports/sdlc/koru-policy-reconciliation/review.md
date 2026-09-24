# KORU and risk-policy reconciliation: issues 22 and 23

## Authority and scope

Base: `758a511aefd37f89f9eec1bfcd3157484bc2566e`. The user requested SDLC processing of #22/#23. On 2026-09-24 they confirmed no KR200 holdings or outstanding orders and requested no-change closure where appropriate. Their final risk-policy correction selected #15 as authoritative, superseding the immediately preceding main-based selection before any #15 body edit.

- [#22 closure and account confirmation](https://github.com/hwanjjang/kis-hl-trading-system/issues/22#issuecomment-5805435290)
- [#15 authority confirmation](https://github.com/hwanjjang/kis-hl-trading-system/issues/15#issuecomment-5805643580)

Scope: documentation, issue disposition and a reviewable PR. No runtime behavior, risk guards, account data or real orders change.

## Triage and investigation

#22 is CLOSED / NOT_PLANNED: no current KR200 position or order requires the blocked management paths. This is user-provided account information, not an exchange query. The offline reproduction remains valid for other accounts with existing exposure; no general allowlist exception is justified by this account's situation.

#23 corrects KORU documentation and reconciles conflicting risk requirements. Main changed the multiplier to 10, but its helper still floors capital and has no production sizing caller. Existing KIS order routing and native trailing management are implemented independently of #15. The older issue's no-routing rationale is outdated, while its documentation-only KIS unit-sizing scope is retained.

## Acceptance and final disposition

| Criterion | Evidence / disposition |
| --- | --- |
| Correct active country exposure | Architecture selects KORU, excludes KR200/EWY, distinguishes ETF/U.S. hours and quote-only KIS mapping. |
| Explain migration | Asset document supplies explicit seed commands and explains git pull does not migrate operational SQLite or close/cancel exposure. |
| Resolve authority | Dated owner-document notes and #15 comment preserve #15's decisions; no issue-body decision reversal. |
| Distinguish target and code | README, strategy and operations explicitly state unfloored target versus current floored helper; no claim of live unit sizing or changed plan limits. |
| Resolve risk semantics | Explicit-stop unit sizing, no preset cumulative unit/add-up caps, trailing-risk reuse, margin report/user decision, KIS 1x scope and short/BTC boundaries documented. |
| Preserve behavior | Only Markdown files changed; no live action or operational DB modification. |

## File-level design and changes

- `README.md`: usage-level distinction between current helper and #15 target.
- `docs/architecture.md`: KORU selection and owner-document link.
- `docs/trade_xyz_assets.md`: explicit seed refresh and account-specific #22 disposition.
- `docs/strategy_execution_design.md`: authoritative target formulas, unit calculation, superseded caps, implementation gaps and historical design status.
- `docs/trading-operations.md`: dated supersession, fixed-stop sizing versus verified risk reuse, no preset cumulative caps, and unchanged current execution boundaries.
- This report: requirements, investigation, acceptance and verification evidence.

Owner files retain their responsibilities from CLAUDE.md; operations links to strategy-owned formulas instead of maintaining another copy. No alternate cap values or new execution authority were invented.

## Verification

1. `python3 -m unittest tests.test_risk tests.test_koru_exposure tests.test_kis_mappings tests.test_trade_xyz_assets tests.test_storage tests.test_trading_hours -q`: 44 tests passed during this documentation task. Only prose changed afterward; no runtime changes required repeating them.
2. Final Markdown checks: balanced fenced blocks and all relative file/heading links passed for the five changed product documents.
3. Functional smoke: ran documented `xyz-assets seed`, `seed-kis` and `seed-ref` through the real CLI against temporary SQLite. Verified KORU tradable/active, KR200 and EWY excluded. No vendor calls or persistent operational DB writes.
4. `git diff --check` passed. Self-review checked the final changes against the full #15 body/comments and current helper/managed-path boundaries.

## Release limits

The dedicated SDLC skill/workflow was unavailable in active tools and searched skill/plugin paths. Repository rules and historical report structure informed this evidence; independent review and formal gate completion are not claimed. Publish as a draft PR, not a merge-ready declaration. #23 remains open until integration. #15 implementation remains open; no KORU live acceptance or account verification was performed.
