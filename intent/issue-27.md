# Issue 27: bounded conditional add

Owner: main agent. Route: implementation / local. Authority: AK's implementation request and issue 27; no live orders, activation, publication or merge.

Implement one immutable, explicitly authorized Hyperliquid long add per signal on an existing account/instrument owner. Reconcile total account balance for sizing independently from available funds. Preserve fixed stops and frozen ATR/watermarks and exit the entire remaining position. Hermes remains responsible for review and notification. Issue 28 partial take-profit is excluded.

Acceptance: AC1 account-total capital and ambiguous-collateral rejection; AC2 completed/fresh condition, bounded authority, exposure and durable replay gate; AC3 partial/completed add with tranche evidence and combined SL/TS, bounded failure; AC4 external-trail migration has no signed mutation and competing/partial exits close residual quantity with scoped cleanup; AC5 CLI/SQLite stub smoke, owner docs and changed-scope tests/diff check. Offline evidence only; no live behavior claim.

## Post-merge correction authority — 2026-09-25

AK requests a comment on issue27 for two reproduced defects, SDLC implementation,
diagram review/update and any needed new diagrams. Follow-up branch starts at
4b558e0; deliver verified corrections through a reviewed follow-up PR, without
merge, live account/order/protection mutation or activation. Reviewer is explicitly
Grok4.7 / high / auto, superseding this task's default SDLC model/medium setting.
Existing iteration counters persist; original local receipts remain historical.

AC2/AC3: cancellation budgets belong to the target entry/add attempt and survive
restart; a prior order's clock cannot prevent a new add's first expiry cancellation.
AC2/AC5: finished owners retire only queued adds with no durable signed attempt;
legacy finished snapshots receive the same cleanup on supervisor reconciliation.
Preserve UNKNOWN reconciliation, per-target bounded retry, verified protection,
full residual exits and all existing AC1–AC5 requirements.
